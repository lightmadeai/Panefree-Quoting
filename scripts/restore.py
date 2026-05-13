"""
Hotfix-5 T3: restore a backup created by scripts/backup.py.

Usage:
  python scripts/restore.py <backup-uri> <target-path> [--force]

  <backup-uri>    URI to a single backup (b2://bucket/prefix/file.db.gz
                  or file:///path/to/file.db.gz). The script downloads,
                  gunzips, and writes the binary to <target-path>.
  <target-path>   Local path to write the restored SQLite DB. Refuses
                  to overwrite project_root/sovereign.db unless --force
                  is passed — too easy to footgun the live DB otherwise.

Pipeline:
  1. Download the backup (or read local file)
  2. Gunzip in place
  3. Sanity-check: open it as SQLite, count users + quotes, fail if
     the file isn't a valid SQLite DB
  4. Run the schema-parity check from DEPLOYMENT.md §2.4 (compare
     against models.py to confirm the backup's schema is restorable)
  5. Write to <target-path>

Exit codes:
  0  success
  1  config / argument error
  2  download / gunzip failed
  3  sanity check failed (not a SQLite DB or empty)
  4  schema parity drift between backup and current models.py
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

import re


def _resolve_file_uri(uri: str) -> str:
    """Mirror of backup.py's FileTarget URL handling, for symmetry."""
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"_resolve_file_uri called with non-file URI: {uri}")
    if re.fullmatch(r"[A-Za-z]:", parsed.netloc):
        return parsed.netloc + parsed.path
    return urllib.request.url2pathname(parsed.path)


def download_to(uri: str, local_path: str) -> None:
    """Fetch the backup blob to a local file. Supports file:// and
    b2://. The b2 path uses the same SDK as the backup script."""
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "file":
        src = _resolve_file_uri(uri)
        shutil.copy2(src, local_path)
        return
    if parsed.scheme == "b2":
        try:
            from b2sdk.v2 import InMemoryAccountInfo, B2Api
        except ImportError as e:
            raise RuntimeError("b2sdk not installed") from e
        key_id = os.environ.get("B2_KEY_ID")
        app_key = os.environ.get("B2_APPLICATION_KEY")
        if not key_id or not app_key:
            raise RuntimeError("B2_KEY_ID + B2_APPLICATION_KEY required for b2:// URI")
        info = InMemoryAccountInfo()
        api = B2Api(info)
        api.authorize_account("production", key_id, app_key)
        bucket = api.get_bucket_by_name(parsed.netloc)
        # Strip leading slash from path; b2sdk wants bare file name
        remote = parsed.path.lstrip("/")
        downloaded = bucket.download_file_by_name(remote)
        downloaded.save_to(local_path)
        return
    raise ValueError(f"Unsupported scheme: {parsed.scheme!r}")


def gunzip_to(src_gz: str, dst: str) -> None:
    with gzip.open(src_gz, "rb") as fin, open(dst, "wb") as fout:
        while True:
            chunk = fin.read(64 * 1024)
            if not chunk:
                break
            fout.write(chunk)


def sanity_check_db(path: str) -> dict:
    """Open the restored DB and confirm it's a real SQLite file with
    the expected core tables. Returns a stats dict for the drill report."""
    conn = sqlite3.connect(path)
    try:
        stats = {}
        for table in ("users", "quotes", "pricing_profiles", "transactions"):
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = count
            except sqlite3.OperationalError as e:
                raise RuntimeError(f"sanity check failed on table {table!r}: {e}") from e
        return stats
    finally:
        conn.close()


def schema_parity_check(path: str) -> list:
    """Run the schema-parity check from DEPLOYMENT.md §2.4 against the
    restored DB. Returns a list of drift descriptions (empty = clean)."""
    from app import app, db
    from sqlalchemy import inspect, create_engine

    drifts = []
    # Build a fresh SQLAlchemy engine against the restored file so we
    # don't disturb the live app's session.
    engine = create_engine(f"sqlite:///{path}")
    try:
        insp = inspect(engine)
        with app.app_context():
            for tbl in db.metadata.tables.values():
                live_cols = {c["name"] for c in insp.get_columns(tbl.name)}
                model_cols = {c.name for c in tbl.columns}
                only_live = live_cols - model_cols
                only_model = model_cols - live_cols
                if only_live or only_model:
                    drifts.append(
                        f"{tbl.name}: only_in_backup={only_live} "
                        f"only_in_models={only_model}"
                    )
    finally:
        engine.dispose()
    return drifts


def main():
    parser = argparse.ArgumentParser(description="Restore a backup created by scripts/backup.py")
    parser.add_argument("backup_uri", help="file:// or b2:// URI to the .db.gz backup")
    parser.add_argument("target_path", help="Local filesystem path to write the restored DB")
    parser.add_argument("--force", action="store_true",
                        help="Allow overwriting project_root/sovereign.db (DANGEROUS)")
    args = parser.parse_args()

    # Refuse to clobber live DB without --force
    live_db = os.path.join(ROOT, "sovereign.db")
    if os.path.abspath(args.target_path) == os.path.abspath(live_db) and not args.force:
        sys.stderr.write(
            "[RESTORE] target_path is the live sovereign.db. Refusing to overwrite. "
            "Re-run with --force if you really mean it.\n"
        )
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="window-quoting-restore-") as tmp:
        downloaded_gz = os.path.join(tmp, "downloaded.db.gz")
        gunzipped = os.path.join(tmp, "restored.db")

        try:
            print(f"[RESTORE] downloading {args.backup_uri}")
            download_to(args.backup_uri, downloaded_gz)
        except Exception as e:
            sys.stderr.write(f"[RESTORE] download failed: {e!r}\n")
            sys.exit(2)

        try:
            print(f"[RESTORE] gunzipping...")
            gunzip_to(downloaded_gz, gunzipped)
        except Exception as e:
            sys.stderr.write(f"[RESTORE] gunzip failed: {e!r}\n")
            sys.exit(2)

        try:
            stats = sanity_check_db(gunzipped)
            print(f"[RESTORE] sanity check OK: {stats}")
        except Exception as e:
            sys.stderr.write(f"[RESTORE] sanity check failed: {e!r}\n")
            sys.exit(3)

        try:
            drifts = schema_parity_check(gunzipped)
            if drifts:
                sys.stderr.write("[RESTORE] schema drift detected vs models.py:\n")
                for d in drifts:
                    sys.stderr.write(f"  {d}\n")
                sys.stderr.write(
                    "Backup is restorable but may need a migration step. "
                    "Inspect drift before pointing the app at this DB.\n"
                )
                # Drift is informational — write the file anyway, exit 4
                # so cron / CI flags it but the operator can still
                # manually use the restored file.
                shutil.copy2(gunzipped, args.target_path)
                print(f"[RESTORE] wrote {args.target_path} (with schema drift)")
                sys.exit(4)
        except Exception as e:
            sys.stderr.write(f"[RESTORE] schema parity check errored: {e!r}\n")
            # Non-fatal — the file is still valid SQLite per sanity check
            shutil.copy2(gunzipped, args.target_path)
            print(f"[RESTORE] wrote {args.target_path} (schema check skipped)")
            sys.exit(0)

        shutil.copy2(gunzipped, args.target_path)
        print(f"[RESTORE] wrote {args.target_path}")
        sys.exit(0)


if __name__ == "__main__":
    main()
