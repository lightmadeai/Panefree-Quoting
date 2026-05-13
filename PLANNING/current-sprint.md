---
label: hotfix-6
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal as sprint-5-ops), Jade (adoption + renumber as hotfix-6 with Inquisitor conditions)
adopted_by: Jade
status: in-progress
audit_status: approved
created: 2026-05-12
depends_on: hotfix-5 (done, PASS)
next_up: production-launch
---

# Current Sprint: Hotfix-6 — Production Gate

**Full draft:** `PLANNING/drafts/hotfix-6.md`
**Audit report:** `PLANNING/audits/hotfix-5-audit.md` (H5 PASS)

## Pipeline Status
- **Hotfix-2:** ✅ DONE, PASS
- **Hotfix-3:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-4:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-5:** ✅ DONE, PASS (4 non-blocking remarks)
- **Hotfix-6:** 🔧 IN PROGRESS — **THE LAUNCH GATE**

## Inquisitor Conditions (All Resolved)
- C1: Relabeled as hotfix-6 under Stabilize — NOT a new Ops phase
- C2: Live Stripe smoke test uses real card + refund
- C3: Post-audit before DNS flip is MANDATORY — the audit IS the launch gate

## Carry-Forward Non-Blocking Remarks
- H3 R1: `.env.example` missing H3 env vars
- H3 R2: `test_account_lifecycle.py` doesn't exist yet
- H5 R1: `[BACKUP-*]` tags not in DEPLOYMENT.md log catalog
- H5 R2: Real B2 round-trip not exercised in-sprint
- H5 R3: Schema dumps accumulate without prune (negligible for v1)
- H5 R4: No app-level functional restore test

## Pre-Launch Checklist (Chris-Sprint)
- [x] Phase 1: Accounts (Postmark, Sentry, UptimeRobot, B2)
- [x] Phase 2: DNS (DKIM, SPF, DMARC, Return-Path)
- [ ] Phase 3: Stripe Live (blocked on H3+H4+H5 merge)
- [ ] Phase 4: Legal (Cookie Policy still needed)
- [ ] Phase 5: DNS Flip → Production