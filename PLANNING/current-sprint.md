---
label: hotfix-5
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal), Jade (adoption with Inquisitor conditions)
adopted_by: Jade
status: done
completed: 2026-05-12
audit_status: pass
audit_note: "All 4 tasks landed. Backup pipeline exercised end-to-end via T3 restore drill (row counts matched live exactly). Regression clean (34/34 unit tests + 13/13 stress probes + locust 2426 reqs 0 failures + pip-audit clean). Awaiting Inquisitor post-audit."
created: 2026-05-12
depends_on: hotfix-3 (mailer.py admin alerts on backup failure)
next_up: hotfix-6
---

# Current Sprint: Hotfix-5 — Backup, Restore & Schema Dump

**Full draft:** `PLANNING/drafts/hotfix-5.md`
**Close-out report:** `PLANNING/done/hotfix-5.md`
**Notes:** `PLANNING/notes/hotfix-5-notes.md`
**Drill report:** `testing/restore-drill-2026-05.md`

## Pipeline Status
- **Hotfix-2:** ✅ DONE, PASS
- **Hotfix-3:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-4:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-5:** ✅ DONE — awaiting Inquisitor post-audit verdict
- **Hotfix-6:** ⏳ READY (depends on H5 merge)

## Inquisitor Conditions (All Resolved)
- H5 C1: B2 for backups (4.6x cheaper than S3)
- H5 C2: Add schema dump alongside binary backup

## Carry-Forward Non-Blocking Remarks
- H3 R1: `.env.example` missing H3 env vars (resolved)
- H3 R2: `test_account_lifecycle.py` doesn't exist yet
- H4 R1: Per-worker rate limit (acceptable v1)
- H4 R2: `/health` doesn't probe externals (by design)

## Execution Order
H5 → H6 (serial, Claude executes)
