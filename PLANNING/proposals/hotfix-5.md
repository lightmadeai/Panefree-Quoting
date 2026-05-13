---
label: hotfix-5
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal for Jade, 2026-05-12)
status: draft
audit_status: draft
created: 2026-05-12
depends_on: hotfix-3 (Sentry capture on backup failure via mailer.py admin alert)
---

# Hotfix-5 — Backup Automation + Restore Drill

## Why

DEPLOYMENT.md §2.3 has a one-line manual pre-deploy backup. That doesn't
cover the 99% of the time when nothing is being deployed but disk could
die anyway. SQLite is a single file — losing it loses every user,
subscription, profile, quote, contact submission. Stripe holds the
billing data, but reconstructing user identity + their business profiles
is a multi-week disaster, and the user-customer trust impact would
probably end the business.

## Goals

- Daily automated backup of `sovereign.db` to an off-server destination
- Tiered retention policy so we don't accumulate cost indefinitely
- A documented + executed restore drill so we know recovery actually works
- Alerting if backup hasn't fired in 36 hours

## Tasks

### T1: Backup script
**touches:** new `scripts/backup.py`, `requirements.txt`, DEPLOYMENT.md
**acceptance:**
- Script does: SQLite `.backup` API (online, atomic, safe even while
  the app is running) → gzip → upload to off-server location.
- Off-server target configurable via env: `BACKUP_DESTINATION`
  supporting `s3://bucket/prefix`, `b2://bucket/prefix`, or `file:///path`
  for local-only dev.
- Cloud credentials via standard env vars: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
  for S3, `B2_KEY_ID` / `B2_APPLICATION_KEY` for B2.
- Backblaze B2 recommended over S3 for cost ($0.005/GB/mo vs $0.023/GB/mo).
  A year of daily backups at ~10MB each is ~3.6GB = $0.02/mo on B2.
- Filename pattern: `sovereign-YYYYMMDD-HHMMSS.db.gz`.
- Exit code 0 on success, non-zero on any failure (cron picks this up).
- Sentry capture on failure (uses `sentry_sdk.capture_exception` from
  Hotfix-4) + email to `ADMIN_EMAIL` so backup-broken-for-a-week doesn't
  slip past.

### T2: Retention policy
**touches:** `scripts/backup.py`
**acceptance:**
- After upload, script enumerates backups in destination and prunes:
  - Keep all daily backups for 7 days
  - Keep one per week (Mondays) for the next 4 weeks
  - Keep one per month (1st of month) for the next 6 months
  - Delete anything older
- Encoded as a pure function (`compute_retention_set(filenames, now)`)
  with unit tests in `testing/test_retention.py`. Deletion is destructive
  and needs to be testable in isolation before being trusted at runtime.
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
- Drill is RUN once during this sprint (not just documented). The drill
  report (number of users restored, time elapsed, any anomalies) gets
  committed to `testing/restore-drill-2026-05.md`. This is the artifact
  Inquisitor uses to verify T3 actually happened.

### T4: Cron / scheduled-task wiring + alerting
**touches:** DEPLOYMENT.md only (the actual cron setup is host-specific)
**acceptance:**
- Documented in DEPLOYMENT.md per hosting option:
  - **Render / Railway**: their cron job feature, daily at 03:00 UTC
  - **DO Droplet / Linode**: standard `crontab -e` entry:
    `0 3 * * * /usr/bin/python3 /opt/window-quoting/scripts/backup.py >> /var/log/backup.log 2>&1`
- Document expected backup runtime (~10s for current DB size),
  expected backup size growth, and how to react to alerts:
  - **Sentry catches** the case where the job ran and crashed.
  - **UptimeRobot Heartbeat** (separate from the /health monitor)
    pings a URL after each successful backup; if no ping in 36 hours,
    alerts. This catches the cron-stopped case.

## Out of scope

- WAL-mode online replication (overkill until multi-region)
- Point-in-time recovery / sub-day granularity (not needed for
  daily-billing software; nightly backups are the standard)
- Encrypted-at-rest backups beyond what the cloud provider does
  (S3 / B2 encrypt by default; add KMS later if compliance requires)
- Migrating to a managed Postgres (significant rewrite; not yet justified)
- Backup of `output/` PDF buckets — those are regenerable from Quote
  rows; explicitly accept the small storage churn risk

## Open questions for Jade / Inquisitor

- B2 vs S3: opinion? Proposal: B2 for cost, but if Thorn already has
  AWS for Resumeforge, sharing one provider is fine.
- Should the backup script also dump the schema separately (in addition
  to the binary `.backup`)? Useful for diagnostics; trivial to add.
- Heartbeat-style monitoring (cron-pings-a-URL) vs. log-watching:
  proposal is heartbeat because it's simpler and host-independent.

## Definition of done

- Backup runs end-to-end against the chosen destination
- One full restore drill executed; report committed
- Retention prune tested via `--dry-run` against real backups +
  unit tests pass on `compute_retention_set`
- Cron / scheduled-task wired and observed firing in the test env
- Sentry + heartbeat alerting wired
- Commits on `hotfix-5` branch
- `notes/hotfix-5-notes.md` captures any design decisions
