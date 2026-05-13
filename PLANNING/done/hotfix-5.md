---
label: hotfix-5
project: window-quoting
phase: stabilize
status: done
created: 2026-05-12
completed: 2026-05-12
audit_status: pending
audit_note: "All 4 tasks landed. Backup pipeline exercised end-to-end via T3 restore drill. Regression clean. Awaiting Inquisitor post-audit."
inquisitor_conditions_resolved:
  C1: "B2 picked as primary cloud target; s3:// explicitly NotImplementedError"
  C2: "Schema dump (sovereign-schema-YYYYMMDD.sql) emitted alongside binary backup"
---

# Hotfix-5 — Backups + Restore Drill (DONE)

## Outcome

4 tasks completed. SQLite now has a daily-automated backup pipeline with tiered retention, a tested restore path, and two-layer alerting. The pipeline was exercised end-to-end during T3 with row counts matching live exactly.

| Task | What | Verification |
|---|---|---|
| T1 | `scripts/backup.py` — SQLite `.backup` → schema dump (C2) → gzip → B2/file upload + heartbeat. Sentry + admin-email on failure | E2E smoke against `file://` produced valid `.db.gz` + readable schema dump |
| T2 | Retention policy (7d / 4w / 6m, earliest-in-slot) + `--dry-run` | 10 unit tests in `testing/test_retention.py`; dry-run smoke confirmed no uploads/deletes |
| T3 | `scripts/restore.py` — download → gunzip → sanity check → schema parity check. Restore drill EXECUTED. | Drill report in `testing/restore-drill-2026-05.md`. Restored DB: users 34 / quotes 52 / profiles 23 / transactions 3 — matched live exactly |
| T4 | DEPLOYMENT.md §11 — daily-backup env vars, per-host cron config, retention table, restore procedure, quarterly drill cadence, two-layer alerting | Documentation-only |

## Regression evidence

- `test_mailer.py` — 9/9 PASS
- `test_sentry_hooks.py` — 10/10 PASS
- `test_health.py` — 5/5 PASS
- `test_retention.py` (NEW) — 10/10 PASS
- `stress_probe.py` — 13/13 probes PASS or expected
- Locust 30u × 45s — **2426 reqs, 0 failures**, p50 16ms / p95 52ms / p99 180ms
- `pip-audit --strict` — no known vulnerabilities

## Commits on `hotfix-5`

```
hotfix-5 T1: backup script (SQLite -> gzip -> upload, with schema dump)
hotfix-5 T2: retention policy unit tests + dry-run smoke
hotfix-5 T3: restore script + executed drill report
hotfix-5 T4: DEPLOYMENT.md §11 backup ops + cron + alerting
```

## What Chris needs at prod-env time

Four new env vars from H5 (all in `.env.example`):

```
BACKUP_DESTINATION       # b2://bucket-name (Inquisitor C1)
B2_KEY_ID                # from Backblaze console -> App Keys
B2_APPLICATION_KEY       # paired with B2_KEY_ID
BACKUP_HEARTBEAT_URL     # from UptimeRobot Heartbeat monitor (optional)
```

Plus the H3 + H4 sets (Postmark + Sentry).

External setup tasks (documented in DEPLOYMENT.md §11):
1. Create B2 bucket + scoped app key
2. Add UptimeRobot Heartbeat monitor (36-hour interval)
3. Wire cron / scheduled task on the chosen host

## Open items for Inquisitor post-audit

1. **Real B2 round-trip not exercised in-sprint.** Drill used `file://`. B2 SDK shares everything below the network boundary with the file path. Chris executes the B2 leg post-deploy.
2. **`s3://` raises `NotImplementedError`** per Inquisitor C1.
3. **Schema dumps accumulate without prune** (tiny — ~5 MB / year).
4. **App-level functional restore drill not executed** — could add Flask boot + stress_probe against restored DB as optional quarterly step.

## Phase status

- Stabilize phase: still active. **H6 is the last sprint before launch.**
- Backlog clean. P4 ("Dynamic Add-Ons") is the only outstanding non-critical item; explicitly post-launch.
