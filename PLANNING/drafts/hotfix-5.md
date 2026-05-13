---
label: hotfix-5
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal), Jade (adoption with Inquisitor conditions)
adopted_by: Jade
status: ready
audit_status: pre-approved (conditional)
created: 2026-05-12
depends_on: hotfix-3 (Sentry capture on backup failure via mailer.py admin alert)
inquisitor_conditions:
  C1: "B2 for v1 unless Chris already has AWS infrastructure. 4.6x cheaper than S3. One provider, one set of credentials."
  C2: "Add schema dump alongside binary backup — trivial (2 lines), invaluable for forensics and migration."
---

# Hotfix-5 — Backup Automation + Restore Drill

## Why

DEPLOYMENT.md §2.3 has a one-line manual pre-deploy backup. That doesn't
cover the 99% of the time when nothing is being deployed but disk could
die anyway. SQLite is a single file — losing it loses every user,
subscription, profile, quote, contact submission. Stripe holds the
billing data, but reconstructing user identity + their business profiles
is a multi-week disaster.

## Goals

- Daily automated backup of `sovereign.db` to an off-server destination
- Tiered retention policy so we don't accumulate cost indefinitely
- A documented + executed restore drill so we know recovery actually works
- Alerting if backup hasn't fired in 36 hours

## Inquisitor Conditions (RESOLVED)

- **C1:** **B2 for v1** unless Chris already has AWS infrastructure for Resumeforge. B2 at $0.005/GB/mo vs S3 at $0.023/GB/mo — 4.6x cheaper. A year of daily backups (~3.6 GB) costs $0.02/mo on B2. Managing two cloud providers for two S3-compatible stores is unnecessary complexity. One provider, one set of credentials.
- **C2:** **Add schema dump** alongside the binary `.backup`. `sqlite3 sovereign.db .schema > sovereign-schema-YYYYMMDD.sql` — 2 lines in the script, ~10-20 KB per dump, negligible storage cost. Invaluable for forensic comparison across backups, manual DB inspection without restoring, and migration planning.

## Tasks

### T1: Backup script
**touches:** new `scripts/backup.py`, `requirements.txt`, DEPLOYMENT.md
**acceptance:**
- Script does: SQLite `.backup` API (online, atomic, safe while app is running) → gzip → upload to off-server location.
- **Schema dump added (Inquisitor C2):** `sqlite3 sovereign.db .schema > sovereign-schema-YYYYMMDD.sql` alongside the binary backup.
- Off-server target configurable via env: `BACKUP_DESTINATION`
  supporting `s3://bucket/prefix`, `b2://bucket/prefix`, or `file:///path`.
- Cloud credentials via standard env vars: `B2_KEY_ID` / `B2_APPLICATION_KEY` for B2 (primary); `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for S3 (if Chris has existing AWS infra).
- **B2 recommended (Inquisitor C1)** — $0.005/GB/mo vs S3 $0.023/GB/mo.
- Filename pattern: `sovereign-YYYYMMDD-HHMMSS.db.gz` + `sovereign-schema-YYYYMMDD.sql`.
- Exit code 0 on success, non-zero on any failure.
- Sentry capture on failure + email to `ADMIN_EMAIL`.

### T2: Retention policy
**touches:** `scripts/backup.py`
**acceptance:**
- After upload, script enumerates backups in destination and prunes:
  - Keep all daily backups for 7 days
  - Keep one per week (Mondays) for the next 4 weeks
  - Keep one per month (1st of month) for the next 6 months
  - Delete anything older
- Encoded as a pure function (`compute_retention_set(filenames, now)`)
  with unit tests in `testing/test_retention.py`.
- `--dry-run` CLI flag prints what would be deleted without doing it.
  First production run uses `--dry-run` until observed correct, then
  removed from cron.

### T3: Restore drill
**touches:** new `scripts/restore.py`, new `testing/restore-drill-2026-05.md`,
  DEPLOYMENT.md
**acceptance:**
- `scripts/restore.py <backup-uri> <target-path>` downloads, gunzips,
  validates schema matches `models.py` (using the schema-parity check
  from DEPLOYMENT §2.4), and writes to a target path. Refuses to
  overwrite `sovereign.db` directly unless `--force` is passed.
- Drill procedure documented step-by-step in DEPLOYMENT.md:
  1. Pick a real recent backup
  2. Restore it to `/tmp/restore-test.db`
  3. Boot the app pointed at the restored DB via temporary env override
  4. Log in as a known user, verify quote history is intact, generate
     a test quote
  5. Tear down the test environment
- Drill is RUN once during this sprint. The drill report committed to
  `testing/restore-drill-2026-05.md`.

### T4: Cron / scheduled-task wiring + alerting
**touches:** DEPLOYMENT.md only
**acceptance:**
- Documented in DEPLOYMENT.md per hosting option:
  - **Render / Railway**: their cron job feature, daily at 03:00 UTC
  - **DO Droplet / Linode**: standard `crontab -e` entry
- Document expected backup runtime (~10s), expected size growth, and
  alert response procedures:
  - **Sentry catches** the case where the job ran and crashed.
  - **UptimeRobot Heartbeat** (separate from /health monitor)
    pings a URL after each successful backup; if no ping in 36 hours,
    alerts. Catches the cron-stopped case.

## Out of scope

- WAL-mode online replication (overkill until multi-region)
- Point-in-time recovery / sub-day granularity
- Encrypted-at-rest backups beyond cloud provider default (S3/B2 encrypt by default)
- Migrating to managed Postgres (significant rewrite)
- Backup of `output/` PDF buckets — regenerable from Quote rows

## Definition of done

- Backup runs end-to-end against the chosen destination
- One full restore drill executed; report committed
- Retention prune tested via `--dry-run` against real backups +
  unit tests pass on `compute_retention_set`
- Cron / scheduled-task wired and observed firing in the test env
- Sentry + heartbeat alerting wired
- Commits on `hotfix-5` branch
- `notes/hotfix-5-notes.md` captures any design decisions