# Hotfix-5 Execution Notes

**Branch:** `hotfix-5` (off master, post-Hotfix-4 merge)
**Executor:** Claude
**Per:** Jade-adopted draft with Inquisitor pre-audit conditions C1 + C2

---

## Decisions, deferrals, and things future-me should know

### T1 — Backup script

- **SQLite `.backup` API, not `cp`.** The `.backup` API is an online,
  atomic snapshot — safe while the app is running, no exclusive lock,
  consistent across mid-transaction reads. A naive `cp sovereign.db`
  during a write window would produce a corrupt file roughly half the
  time. The API is one Python call (`src.backup(dst)`) so the cost of
  doing it right is zero.

- **`b2sdk` only used by the backup script.** Flask app doesn't import
  it. Listed in `requirements.txt` so `pip install -r` on the host
  covers the cron job too. Could split into `requirements-backup.txt`
  later if the dep surface grows; not worth a separate file for one
  package.

- **Schema dump via subprocess + Python fallback.** The `sqlite3 .schema`
  CLI produces cleaner output than rolling our own from
  `sqlite_master`, but the CLI isn't always installed (CI containers,
  some minimal images). Try CLI first, fall back to Python on
  `FileNotFoundError` / timeout. Tested both paths during local smoke —
  the dev environment hit the Python fallback because Windows Python
  doesn't ship the sqlite3 CLI.

- **File URL parsing is platform-fragile.** `file:///tmp/x` parses
  differently on POSIX vs Windows vs `$PWD`-concatenated MSYS. The
  FileTarget handles three variants (POSIX absolute, Windows drive-
  letter-in-path, malformed drive-letter-in-netloc). Found by
  silently writing to a relative `tmp/h5-backup-test/` under cwd
  during the first smoke. Bug fix landed in same commit as T1.

- **`s3://` raises NotImplementedError.** Inquisitor C1 picked B2;
  adding boto3 + an S3Target class is straightforward when AWS becomes
  the right fit, but until then leaving s3:// as a loud no-go beats
  silently failing or pulling in a 50MB dep we don't use.

### T2 — Retention policy

- **Pure function design.** `compute_retention_set(filenames, now)`
  takes timestamps and returns `(keep, delete)` lists. No I/O, no side
  effects. The 10 unit tests in `testing/test_retention.py` lock the
  policy in isolation. Deletion is destructive — testing the policy
  before any real deletes was non-negotiable.

- **"Earliest in slot" for weekly/monthly tiers.** The function picks
  the EARLIEST backup in each ISO-week / calendar-month slot, not the
  latest. Rationale: the slot-boundary backup (Monday for weeks, 1st
  for months) is what the slot name implies. Picking latest would
  give "the closest-to-now backup that still happens to be in the
  slot," which drifts depending on when the prune runs. Earliest is
  deterministic and matches operator mental model.

- **`--dry-run` does NOT upload either.** Originally I had dry-run
  only suppress the delete step. Better: suppress both, so the first
  prod run with `--dry-run` is a true preview. The cost is one extra
  cron invocation when you're confident; trivial.

- **Schema dumps are NOT retention-managed.** The function ignores
  filenames that don't match the backup pattern. Schema dumps
  accumulate forever — fine for v1 because they're tiny (~10-20 KB
  each, ~5 MB / year). If it ever becomes a concern, add a
  parallel `compute_schema_retention_set` with looser rules.

### T3 — Restore drill

- **Drill ran end-to-end during T3 commit.** Real data, real backup,
  real restore. Row counts matched live exactly: users 34, quotes 52,
  pricing_profiles 23, transactions 3. Report committed to
  `testing/restore-drill-2026-05.md`.

- **Drill used `file://`, not B2.** Inquisitor's C1 puts B2 as the
  primary target, but the b2sdk network leg requires real credentials
  and shouldn't be exercised in a sprint-time drill. The code paths
  (upload, list, delete) share everything below the b2sdk boundary
  with the file path. Chris executes the B2 round-trip drill himself
  post-deploy — same option-(b) pattern as H3 / H4 live smokes.

- **`restore.py` refuses to overwrite live `sovereign.db` without --force.**
  Too easy to footgun by typo. The DEPLOYMENT.md restore procedure
  explicitly does "restore to /tmp first, manually swap" so operators
  always have an inspection window.

- **Schema parity drift = exit 4, not exit 0.** If the backup is from
  an older schema version (e.g. pre-H3 columns), `restore.py` still
  writes the file but exits non-zero. The operator gets the data but
  is loudly told they may need a migration step. Matters more in 6
  months than now — schema is stable across H1-H5.

### T4 — Cron + alerting

- **Two layers of alerting** — Sentry on crash + UptimeRobot Heartbeat
  on success. Either one alone has a blind spot:
  - Sentry only: doesn't catch "cron daemon never started the job"
  - Heartbeat only: doesn't differentiate "script crashed at line 30"
    from "cron stopped firing entirely"
  - Both together: full coverage of both failure modes.

- **36-hour heartbeat threshold.** Daily backups means a 24-hour
  interval. One miss (cron daemon hiccup, host reboot, etc.) shouldn't
  page. Two misses (~36 hours) means something is actually broken.
  Tunable in UptimeRobot if pattern shows we want tighter.

---

## What Chris needs at prod-env time

Four new env vars from H5 (all in `.env.example`):

| Var | Source | Notes |
|---|---|---|
| `BACKUP_DESTINATION` | choose | `b2://bucket-name` for v1 |
| `B2_KEY_ID` | Backblaze console → App Keys | Scope to backup bucket only |
| `B2_APPLICATION_KEY` | Backblaze console → App Keys | Paired with key_id |
| `BACKUP_HEARTBEAT_URL` | UptimeRobot Heartbeat monitor | Optional but recommended |

Plus the H3 + H4 sets (POSTMARK_*, EMAIL_*, ADMIN_EMAIL, SENTRY_DSN).

Plus the existing test kill switches (MUST NOT be set in prod):
`DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED`.

---

## Open items deliberately deferred

- **Real B2 network leg smoke** — Chris executes post-deploy with
  actual keys. Same option-(b) pattern as H3/H4.
- **Multi-day retention drill** — `test_retention.py` exercises the
  policy in isolation across simulated 1-year histories. A real
  365-day drill would take 365 days; not practical for a sprint-time
  artifact. The unit tests are the equivalent confidence.
- **App-level functional restore drill** — Drill confirms row counts;
  doesn't spin a Flask app against the restored DB. Could add this
  to the quarterly drill procedure as an optional step.
- **`s3://` target** — Not implemented; Inquisitor C1 picked B2.
- **Encrypted-at-rest backups beyond cloud default** — B2 + S3
  encrypt at rest by default. KMS / customer-managed keys could be
  added if compliance ever requires.
- **WAL replication / PITR** — Overkill for daily-billing software.

---

## Inquisitor conditions — both resolved

- **C1** (B2 for v1 unless Chris already has AWS infra) — `B2Target`
  implemented as the primary cloud target. `s3://` explicitly
  unimplemented to keep the dep surface focused on one provider.
- **C2** (schema dump alongside binary backup) — `dump_schema()` runs
  before gzip, emits `sovereign-schema-YYYYMMDD.sql` next to the
  `.db.gz`. ~10-20 KB per dump.

---

## Verification summary

| Check | Result |
|---|---|
| `testing/test_mailer.py` | 9/9 pass |
| `testing/test_sentry_hooks.py` | 10/10 pass |
| `testing/test_health.py` | 5/5 pass |
| `testing/test_retention.py` (NEW) | 10/10 pass |
| `testing/stress_probe.py` (P1, P5, P6, P8, P9/P10, P11, P12, P13, P14, P15, P16) | All PASS or expected status |
| Locust 30u × 45s | 2426 reqs, 0 failures, p50 16ms / p95 52ms / p99 180ms |
| `pip-audit --requirement requirements.txt --strict` | No known vulnerabilities |
| `python scripts/backup.py` (file:// target) | Snapshot + schema dump + gzip + upload + prune OK |
| `python scripts/backup.py --dry-run` | Previews without uploading or deleting |
| `python scripts/restore.py file://... /sandbox.db` | Downloads, gunzips, sanity-checks, schema-parity-checks |
| Restore drill row-count match | users/quotes/profiles/transactions all match live exactly |
| App boots cleanly post-H5 | Yes; only `[MAIL]` token-unset error (correct for local) |
