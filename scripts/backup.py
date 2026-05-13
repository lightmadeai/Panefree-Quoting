"""
Hotfix-5 T1+T2: daily SQLite backup with tiered retention.

Runs from cron / scheduled task. Pipeline:
  1. SQLite .backup API → write atomic snapshot to /tmp
  2. Schema dump (Inquisitor C2) → sqlite3 .schema output to /tmp
  3. gzip the binary backup
  4. Upload both to BACKUP_DESTINATION (b2:// or s3:// or file://)
  5. Prune per the retention policy (7 daily + 4 weekly + 6 monthly)
  6. Ping heartbeat URL on success (T4 alerting)

Exit codes:
  0  success
  1  config error (missing env vars)
  2  backup snapshot failed
  3  upload failed
  4  retention prune failed

On any non-zero exit, the script sends an admin alert via the app's
mailer (Hotfix-3 T5) and captures to Sentry (Hotfix-4 T1) if SENTRY_DSN
is configured.

Usage:
  python scripts/backup.py                 # full pipeline
  python scripts/backup.py --dry-run       # T2: preview prune deletions
  python scripts/backup.py --skip-prune    # backup only, no prune
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from typing import Iterable, List, Tuple

# Allow importing app modules (mailer, config) from project root
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)


# ---------- Filenames ----------
BACKUP_FILENAME_RE = re.compile(
    r"^sovereign-(?P<date>\d{8})-(?P<time>\d{6})\.db\.gz$"
)
SCHEMA_FILENAME_RE = re.compile(
    r"^sovereign-schema-(?P<date>\d{8})\.sql$"
)


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _backup_basename(now: _dt.datetime) -> str:
    return f"sovereign-{now.strftime('%Y%m%d-%H%M%S')}.db.gz"


def _schema_basename(now: _dt.datetime) -> str:
    return f"sovereign-schema-{now.strftime('%Y%m%d')}.sql"


# ---------- Retention (T2) ----------
def compute_retention_set(filenames: Iterable[str], now: _dt.datetime) -> Tuple[List[str], List[str]]:
    """
    Pure function. Given the current list of backup filenames in the
    destination and the current UTC datetime, return:
      (keep_list, delete_list)

    Retention policy (T2):
      - All daily backups within 7 days
      - One backup per ISO week (Monday-anchored) within the next 4 weeks
      - One backup per calendar month (1st of month) within the next 6 months
      - Delete anything older or any duplicate within a slot

    Filenames not matching BACKUP_FILENAME_RE are ignored — schema dumps
    and any non-backup artifacts pass through untouched.

    The "one per week / month" pick is deterministic: take the EARLIEST
    backup in each slot. Picking earliest (vs latest) keeps the
    slot-boundary backup, which is the one whose timestamp matches the
    slot name — easier to reason about.
    """
    parsed: List[Tuple[_dt.datetime, str]] = []
    for f in filenames:
        m = BACKUP_FILENAME_RE.match(os.path.basename(f))
        if not m:
            continue
        try:
            ts = _dt.datetime.strptime(
                m.group("date") + m.group("time"), "%Y%m%d%H%M%S",
            )
        except ValueError:
            continue
        parsed.append((ts, f))

    if not parsed:
        return ([], [])

    parsed.sort()  # oldest first

    # Slot calculations relative to `now`
    seven_days_ago = now - _dt.timedelta(days=7)
    five_weeks_ago = now - _dt.timedelta(weeks=5)  # 7 daily + 4 weekly buffer
    seven_months_ago = now - _dt.timedelta(days=31 * 7)  # generous monthly buffer

    keep_set = set()

    # Daily tier — keep everything in the last 7 days
    for ts, path in parsed:
        if ts >= seven_days_ago:
            keep_set.add(path)

    # Weekly tier — one per ISO-week for 7-35 days back. ISO week starts Monday.
    by_week: dict = {}
    for ts, path in parsed:
        if not (five_weeks_ago <= ts < seven_days_ago):
            continue
        iso_year, iso_week, _ = ts.isocalendar()
        key = (iso_year, iso_week)
        if key not in by_week or ts < by_week[key][0]:
            by_week[key] = (ts, path)
    for _, path in by_week.values():
        keep_set.add(path)

    # Monthly tier — one per calendar month for ~5-7 months back
    by_month: dict = {}
    for ts, path in parsed:
        if not (seven_months_ago <= ts < five_weeks_ago):
            continue
        key = (ts.year, ts.month)
        if key not in by_month or ts < by_month[key][0]:
            by_month[key] = (ts, path)
    for _, path in by_month.values():
        keep_set.add(path)

    all_paths = {p for _, p in parsed}
    delete_set = all_paths - keep_set
    return (sorted(keep_set), sorted(delete_set))


# ---------- Backup pipeline ----------
def take_snapshot(source_db: str, target_path: str) -> None:
    """
    Use SQLite's online .backup API to write an atomic snapshot. Safe
    while the app is running — no exclusive lock, no inconsistency
    risk from a concurrent transaction.
    """
    src = sqlite3.connect(source_db)
    dst = sqlite3.connect(target_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()


def dump_schema(source_db: str, target_path: str) -> None:
    """
    Inquisitor C2: human-readable schema dump alongside the binary
    backup. Lets ops compare schemas across backups without restoring,
    and gives migration planning a paper trail.

    Uses `sqlite3 <db> .schema` via subprocess because the sqlite3 CLI
    formats this more cleanly than rolling our own from the Python
    bindings. Falls back to a Python-side dump if the CLI is missing.
    """
    try:
        result = subprocess.run(
            ["sqlite3", source_db, ".schema"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: pure Python (no sqlite3 CLI on this host)
    conn = sqlite3.connect(source_db)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
        with open(target_path, "w", encoding="utf-8") as f:
            for (sql,) in rows:
                f.write(sql)
                f.write(";\n\n")
    finally:
        conn.close()


def gzip_file(src: str, dst: str) -> None:
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        # 64KB chunks — small DB so we'd be done in one read anyway,
        # but the streaming pattern keeps memory flat if the DB grows.
        while True:
            chunk = fin.read(64 * 1024)
            if not chunk:
                break
            fout.write(chunk)


# ---------- Upload targets ----------
class UploadTarget:
    """Common interface for destination backends. Subclasses implement
    list / upload / delete. Constructor parses the URI; methods raise
    on auth or network failure (caller maps to exit code 3)."""
    def list(self) -> List[str]:
        raise NotImplementedError
    def upload(self, local_path: str, remote_basename: str) -> None:
        raise NotImplementedError
    def delete(self, remote_path: str) -> None:
        raise NotImplementedError


class FileTarget(UploadTarget):
    """file:///path target — for local-dev tests and as the "I have a
    NAS mounted" option."""
    def __init__(self, path: str):
        self.path = path
        os.makedirs(path, exist_ok=True)

    def list(self) -> List[str]:
        if not os.path.isdir(self.path):
            return []
        return [os.path.join(self.path, n) for n in os.listdir(self.path)]

    def upload(self, local_path: str, remote_basename: str) -> None:
        dest = os.path.join(self.path, remote_basename)
        with open(local_path, "rb") as src, open(dest, "wb") as dst:
            while True:
                chunk = src.read(64 * 1024)
                if not chunk:
                    break
                dst.write(chunk)

    def delete(self, remote_path: str) -> None:
        try:
            os.remove(remote_path)
        except FileNotFoundError:
            pass


class B2Target(UploadTarget):
    """B2 bucket target (Inquisitor C1 — primary cloud destination).

    Auth via B2_KEY_ID + B2_APPLICATION_KEY env vars (standard B2 SDK
    env conventions). b2sdk handles retries + multipart upload at the
    SDK layer; we just call upload_local_file."""
    def __init__(self, bucket: str, prefix: str):
        try:
            from b2sdk.v2 import InMemoryAccountInfo, B2Api
        except ImportError as e:
            raise RuntimeError(
                "b2sdk not installed — pip install b2sdk (also in requirements.txt)"
            ) from e
        key_id = os.environ.get("B2_KEY_ID")
        app_key = os.environ.get("B2_APPLICATION_KEY")
        if not key_id or not app_key:
            raise RuntimeError(
                "B2_KEY_ID and B2_APPLICATION_KEY env vars required for b2:// target"
            )
        info = InMemoryAccountInfo()
        api = B2Api(info)
        api.authorize_account("production", key_id, app_key)
        self.bucket = api.get_bucket_by_name(bucket)
        self.prefix = prefix.strip("/")

    def _full_remote(self, basename: str) -> str:
        return f"{self.prefix}/{basename}" if self.prefix else basename

    def list(self) -> List[str]:
        return [
            f.file_name
            for f, _ in self.bucket.ls(folder_to_list=self.prefix, recursive=False)
        ]

    def upload(self, local_path: str, remote_basename: str) -> None:
        self.bucket.upload_local_file(
            local_file=local_path,
            file_name=self._full_remote(remote_basename),
        )

    def delete(self, remote_path: str) -> None:
        # B2 delete requires file_id; resolve from name.
        try:
            file_versions = list(
                self.bucket.list_file_versions(remote_path)
            )
        except Exception:
            file_versions = []
        for fv in file_versions:
            self.bucket.delete_file_version(fv.id_, fv.file_name)


def make_target(destination: str) -> UploadTarget:
    """Parse the BACKUP_DESTINATION env URI and return the right target.
    `file://`, `b2://bucket/prefix`. S3 deferred (Inquisitor C1 said
    B2-first; can add later if Chris ever moves to AWS)."""
    parsed = urllib.parse.urlparse(destination)
    if parsed.scheme == "file":
        # File URL parsing is platform-fragile. The canonical forms:
        #   POSIX:    file:///absolute/path
        #   Windows:  file:///C:/path/to/dir  (THREE slashes; drive in path)
        # Common malformed inputs we accept:
        #   file://C:/path  (drive in netloc — happens when concatenating
        #                    bash's "$PWD" on MSYS into a URL)
        # Strategy: if netloc looks like a Windows drive letter, rejoin
        # it with the path; otherwise use url2pathname on the path alone.
        if re.fullmatch(r"[A-Za-z]:", parsed.netloc):
            raw = parsed.netloc + parsed.path
        else:
            raw = urllib.request.url2pathname(parsed.path)
        return FileTarget(raw)
    if parsed.scheme == "b2":
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
        return B2Target(bucket, prefix)
    if parsed.scheme == "s3":
        raise NotImplementedError(
            "s3:// destination not implemented in v1 — Inquisitor C1 picked "
            "B2 as the primary cloud target. Add boto3 + an S3Target class "
            "when AWS is the better fit."
        )
    raise ValueError(
        f"Unknown BACKUP_DESTINATION scheme: {parsed.scheme!r}. "
        "Expected file://, b2://, or s3://"
    )


# ---------- Orchestration ----------
def _emit_failure_alert(stage: str, exc: BaseException) -> None:
    """Send admin alert via the app's mailer + Sentry capture. Best-
    effort — if alerting itself fails, the script's non-zero exit still
    lands in cron's local log."""
    try:
        import mailer  # noqa: F401
        import config  # noqa: F401
        from app import _notify_admin  # uses mailer's admin alert template
        _notify_admin(
            alert_tag="BACKUP-FAILED",
            subject_summary=f"Backup stage '{stage}' failed",
            body_markdown=(
                f"Stage: {stage}\n"
                f"Error: {exc!r}\n"
                f"Time:  {_now_utc().isoformat()}Z\n"
                f"\n"
                f"Action: SSH the host, run `python scripts/backup.py`\n"
                f"manually, inspect output. If repeated, file a sprint.\n"
            ),
        )
    except Exception as alert_err:
        sys.stderr.write(
            f"[BACKUP-ALERT-FAILED] could not send admin alert for "
            f"{stage} failure: {alert_err!r}\n"
        )
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


def _ping_heartbeat() -> None:
    """T4: optional heartbeat ping after successful backup. UptimeRobot
    Heartbeat URL goes in BACKUP_HEARTBEAT_URL env. No-op if unset."""
    url = os.environ.get("BACKUP_HEARTBEAT_URL")
    if not url:
        return
    try:
        import requests
        requests.get(url, timeout=10)
    except Exception as e:
        sys.stderr.write(
            f"[BACKUP-HEARTBEAT-FAILED] {e!r} (backup itself succeeded)\n"
        )


def run(dry_run: bool, skip_prune: bool) -> int:
    """Returns exit code. 0 = success."""
    source_db = os.path.join(ROOT, "sovereign.db")
    if not os.path.exists(source_db):
        sys.stderr.write(f"[BACKUP] source DB not found: {source_db}\n")
        return 1

    destination = os.environ.get("BACKUP_DESTINATION")
    if not destination:
        sys.stderr.write(
            "[BACKUP] BACKUP_DESTINATION env unset. Expected file://, b2://, "
            "or s3:// URI.\n"
        )
        return 1

    now = _now_utc()
    backup_name = _backup_basename(now)
    schema_name = _schema_basename(now)

    try:
        target = make_target(destination)
    except Exception as e:
        sys.stderr.write(f"[BACKUP] target init failed: {e!r}\n")
        _emit_failure_alert("target_init", e)
        return 1

    # Snapshot + schema dump to a temp dir, then upload.
    with tempfile.TemporaryDirectory(prefix="window-quoting-backup-") as tmp:
        binary_path = os.path.join(tmp, "snapshot.db")
        binary_gz = os.path.join(tmp, backup_name)
        schema_path = os.path.join(tmp, schema_name)

        try:
            take_snapshot(source_db, binary_path)
            dump_schema(source_db, schema_path)
            gzip_file(binary_path, binary_gz)
        except Exception as e:
            sys.stderr.write(f"[BACKUP] snapshot failed: {e!r}\n")
            _emit_failure_alert("snapshot", e)
            return 2

        if dry_run:
            print(f"[DRY-RUN] would upload: {backup_name}, {schema_name}")
        else:
            try:
                target.upload(binary_gz, backup_name)
                target.upload(schema_path, schema_name)
                print(f"[BACKUP-UPLOADED] {backup_name} + {schema_name}")
            except Exception as e:
                sys.stderr.write(f"[BACKUP] upload failed: {e!r}\n")
                _emit_failure_alert("upload", e)
                return 3

    # Retention prune
    if not skip_prune:
        try:
            existing = target.list()
            keep, delete = compute_retention_set(existing, now)
            for path in delete:
                if dry_run:
                    print(f"[DRY-RUN] would delete: {path}")
                else:
                    target.delete(path)
                    print(f"[BACKUP-PRUNED] {path}")
        except Exception as e:
            sys.stderr.write(f"[BACKUP] retention prune failed: {e!r}\n")
            _emit_failure_alert("prune", e)
            return 4

    _ping_heartbeat()
    print(f"[BACKUP-DONE] {now.isoformat()}Z")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Daily SQLite backup pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview upload + prune without doing them")
    parser.add_argument("--skip-prune", action="store_true",
                        help="Backup only; skip the retention prune step")
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run, skip_prune=args.skip_prune))


if __name__ == "__main__":
    main()
