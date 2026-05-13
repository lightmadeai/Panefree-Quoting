---
label: hotfix-4
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal), Jade (adoption with Inquisitor conditions)
adopted_by: Jade
status: done
completed: 2026-05-12
audit_status: pending
audit_note: "All 5 tasks landed (T0 added mid-sprint with Chris's explicit authorization following the panefreequoting.com domain decision). Regression clean (24/24 unit tests, 13/13 stress probes, locust 2387 reqs 0 failures). Awaiting Inquisitor post-audit."
created: 2026-05-12
depends_on: hotfix-3 (done, PASS)
next_up: hotfix-5
---

# Current Sprint: Hotfix-4 — Observability: Sentry + Health Check + Ops Runbook

**Full draft:** `PLANNING/drafts/hotfix-4.md`
**Close-out report:** `PLANNING/done/hotfix-4.md`
**Notes (incl. T0 rationale):** `PLANNING/notes/hotfix-4-notes.md`

## Pipeline Status
- **Hotfix-2:** ✅ DONE, PASS (post-audit complete)
- **Hotfix-3:** ✅ DONE, PASS (post-audit complete, 3 non-blocking remarks)
- **Hotfix-4:** ✅ DONE — awaiting Inquisitor post-audit verdict
- **Hotfix-5:** ⏳ READY (depends on H3+H4 merge)
- **Hotfix-6:** ⏳ READY (depends on H3+H4+H5 merge)

## Inquisitor Conditions (All Resolved)
- H4 C1: Sentry free tier accepted + `before_send` rate limiter cap at 500 errors/hour
- H4 C2: Email-only alerts for v1 + Sentry mobile app (free). No SMS/Twilio.

## Execution Order
H4 → H5 → H6 (serial, Claude executes)

## Non-Blocking Remarks from H3 (Carry-Forward)
- R1: `.env.example` missing H3 env vars (POSTMARK_SERVER_TOKEN, EMAIL_FROM, EMAIL_FROM_NAME, ADMIN_EMAIL)
- R2: `test_account_lifecycle.py` doesn't exist yet (defer to ops sprint)
- R3: `[EMAIL-VERIFICATION]` log line includes full verify URL (acceptable for v1)