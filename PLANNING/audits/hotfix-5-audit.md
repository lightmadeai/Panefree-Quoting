---
label: hotfix-5
project: window-quoting
auditor: inquisitor
date: 2026-05-13
verdict: PASS
blocking_count: 0
nonblocking_count: 4
---

# Hotfix-5 Post-Audit — Backup Automation + Restore Drill + Schema Dump

**Auditor:** The Inquisitor
**Date:** 2026-05-13
**Branch:** `hotfix-5` (5 commits: T1-T4 + close-out)
**Verdict:** ✅ PASS — all 4 implemented tasks verified against acceptance criteria. 0 blocking findings. 4 non-blocking remarks.

---

## Task Verification Matrix

| Task | Description | Verified | Notes |
|------|-------------|:--------:|-------|
| T1 | Backup script (`scripts/backup.py`) | ✅ | SQLite `.backup` API (atomic, safe while app running). Schema dump via `dump_schema()` with CLI+Python fallback. gzip compression. B2 upload via `b2sdk`. `s3://` explicitly raises `NotImplementedError` (C1 honored). Filename pattern: `sovereign-YYYYMMDD-HHMMSS.db.gz` + `sovereign-schema-YYYYMMDD.sql`. Heartbeat ping. Sentry + admin email on failure. Exit code 0/non-zero. |
| T2 | Retention policy | ✅ | `compute_retention_set()` pure function with 10 unit tests. 7d daily / 4w weekly (earliest per ISO-week) / 6m monthly policy. `--dry-run` suppresses both upload AND delete. Schema dumps not retention-managed (acceptable — ~5MB/year). |
| T3 | Restore script + drill | ✅ | `scripts/restore.py` downloads, gunzips, sanity-checks (4 core tables), schema-parity-checks against `models.py`. Refuses to overwrite `sovereign.db` without `--force`. Exit codes: 0=success, 1=config, 2=download/gunzip, 3=sanity, 4=drift. Drill executed end-to-end with row counts matching live (34 users, 52 quotes, 23 profiles, 3 transactions). |
| T4 | DEPLOYMENT.md §11 + cron + alerting | ✅ | Daily backup env vars documented (B2_KEY_ID, B2_APPLICATION_KEY, BACKUP_DESTINATION, BACKUP_HEARTBEAT_URL). Per-host cron config (Render/Railway/VPS). Two-layer alerting: Sentry on crash + UptimeRobot Heartbeat on success (36h threshold). Restore procedure step-by-step. Quarterly drill cadence. |

---

## Inquisitor Conditions Verification

| Condition | Status | Evidence |
|-----------|:------:|---------|
| C1: B2 for v1 unless Chris has AWS infra | ✅ PASS | `B2Target` implemented. `s3://` raises `NotImplementedError` with clear message. `b2sdk~=2.12.0` in requirements.txt. |
| C2: Schema dump alongside binary backup | ✅ PASS | `dump_schema()` runs before gzip. Emits `sovereign-schema-YYYYMMDD.sql`. ~10-20 KB each. Uploaded alongside `.db.gz`. |

---

## T5 (verify_backup.py) — Not Implemented

The post-audit task file listed T5 (Backup Integrity Verification) with `scripts/verify_backup.py`. This task was **not in the adopted sprint scope** — the draft, close-out report, and notes all reference 4 tasks (T1-T4). The functionality is covered by:

1. **`restore.py` sanity_check_db()** — verifies DB integrity by opening and querying 4 core tables
2. **`restore.py` schema_parity_check()** — compares restored schema against `models.py`
3. **Quarterly drill procedure** (DEPLOYMENT.md §11.4) — includes step 4 "confirm schema parity check passed"

**Verdict:** No gap. T5 was not in scope and the verification intent is covered by existing tooling.

---

## T3 `--list` and `--timestamp` flags — Not Implemented

The task file mentioned `--list` and `--timestamp` flags for restore.py. These were **not in the adopted draft**. The restore script takes a direct URI argument instead, which is the safer pattern (explicit restore target > implicit selection). Listing backups is available via B2 dashboard.

**Verdict:** Acceptable. No operational gap.

---

## Regression Verification

- **Unit tests:** 34/34 pass (9 mailer + 10 Sentry + 5 health + 10 retention)
- **Stress probes:** 13/13 pass
- **Locust:** 2426 reqs, 0 failures, p50 16ms / p95 52ms / p99 180ms
- **pip-audit --strict:** No known vulnerabilities
- **Drill:** Restore drill executed end-to-end, row counts match live exactly

---

## Non-Blocking Remarks

### R1: `[BACKUP-*]` Tags Not in Log Catalog
`scripts/backup.py` uses structured `[BACKUP]`, `[BACKUP-UPLOADED]`, `[BACKUP-DONE]`, `[BACKUP-FAILED]`, `[BACKUP-ALERT-FAILED]`, `[BACKUP-HEARTBEAT-FAILED]`, `[BACKUP-PRUNED]` tags (stdout/stderr). These are NOT documented in DEPLOYMENT.md §9 Log Catalog, which only covers `app.logger.*` tags. **Recommendation:** Add a §9.1 subsection for script-level tags, or extend the catalog table to include backup script tags. Operators need to know what `[BACKUP-FAILED]` means when grepping logs.

### R2: Real B2 Round-Trip Not Exercised In-Sprint
Drill used `file://` target. B2 network leg requires real credentials. Chris will execute B2 round-trip post-deploy (same pattern as H3/H4 live smokes). **Acceptable.** The code paths share everything below the `b2sdk` boundary with the file target.

### R3: Schema Dumps Accumulate Without Prune
`compute_retention_set()` ignores non-backup filenames, so `sovereign-schema-*.sql` files accumulate indefinitely. At ~10-20 KB each (~5 MB/year), this is negligible for v1. **Recommendation:** Consider adding schema dump cleanup to a future sprint when B2 costs become a concern.

### R4: No App-Level Functional Restore Test
The drill verifies row counts match live but doesn't boot Flask against the restored DB and run `stress_probe.py`. The notes acknowledge this and offer it as an optional quarterly drill step. **Acceptable for v1** — `.backup` API is byte-equivalent to the source, so functional differences would require gzip corruption (caught by gunzip) or `restore.py` logic bugs (caught by sanity check).

---

## Summary

| Category | Count |
|----------|-------|
| 🔴 Blocking | 0 |
| 🟡 Non-Blocking | 4 |
| ✅ Tasks Verified | 4/4 (in scope) |
| ✅ Conditions Met | 2/2 |
| ℹ️ Out-of-Scope | 2 (T5 verify_backup.py, --list/--timestamp flags) |

**Verdict: ✅ PASS** — Hotfix-5 is approved for merge. All in-scope acceptance criteria met, both Inquisitor conditions satisfied, no blocking findings. Restore drill executed successfully with live data. Proceed to H6 (deployment).