---
label: hotfix-3
project: window-quoting
phase: stabilize
status: done
completed: 2026-05-12
audit_status: pending
created: 2026-05-12
depends_on: hotfix-2 (done, PASS)
next_up: hotfix-4
---

# Current Sprint: Hotfix-3 — User Access Lifecycle

**Full draft:** `PLANNING/drafts/hotfix-3.md`
**Close-out report:** `PLANNING/done/hotfix-3.md`

## Pipeline Status
- **Hotfix-2:** ✅ DONE, PASS (post-audit complete)
- **Hotfix-3:** ✅ DONE — awaiting Inquisitor post-audit verdict
- **Hotfix-4:** ⏳ READY (depends on H3 merge)
- **Hotfix-5:** ⏳ READY (depends on H3 merge)
- **Hotfix-6:** ⏳ READY (depends on H3+H4+H5 merge, relabeled from sprint-5-ops)

## Chris-Sprint
Chris's personal production-readiness checklist: `PLANNING/chris-sprint.md`
**Phase 1 (Accounts) can start NOW** — Postmark, Sentry, UptimeRobot, B2 bucket.

## Inquisitor Conditions (All Resolved)
- H3: Postmark confirmed, hard delete for accounts, /resend-verification logged-in-only
- H4: Sentry free tier + 500/hr rate cap, email-only alerts
- H5: B2 for backups, add schema dump
- H6: Relabeled as hotfix-6 (not a new phase), real card Stripe test, post-audit before DNS flip

## Execution Order
H3 → H4 → H5 → H6 (serial, Claude executes)