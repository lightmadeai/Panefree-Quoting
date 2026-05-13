---
label: hotfix-7
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal — awaiting Jade adoption)
adopted_by: pending
status: proposed
audit_status: pre-audit-pending
created: 2026-05-13
depends_on: hotfix-6 (DONE 2026-05-13, awaiting Inquisitor post-audit)
next_up: production launch + post-launch monitoring
---

# Current Sprint: Hotfix-7 — Launch Execution + Deferred Polish

**Full proposal:** `PLANNING/proposals/hotfix-7.md` (awaiting Jade adoption → moves to `drafts/` when adopted)
**Hotfix-6 close-out:** `PLANNING/done/hotfix-6.md`
**Hotfix-6 notes (for Inquisitor):** `PLANNING/notes/hotfix-6-notes.md`

## Pipeline Status
- **Hotfix-2:** ✅ DONE, PASS
- **Hotfix-3:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-4:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-5:** ✅ DONE, PASS (4 non-blocking remarks)
- **Hotfix-6:** ✅ DONE — awaiting Inquisitor post-audit verdict
- **Hotfix-7:** 🔧 PROPOSED — the actual launch event

## Why this sprint exists

Hotfix-6 enabled the cutover (live Stripe pipeline working, persistent DB, CSP fixes, webhook handler reliability). External blockers (Postmark approval ~1-2 days, Inquisitor cookie policy audit, Inquisitor H6 post-audit) prevent the DNS-flip launch event from landing inside H6. Closing H6 as "cutover ENABLED" and opening H7 as "cutover EXECUTED + polish" maps cleanly to the actual phase boundary without blocking opportunistic work on a stale `in-progress` H6.

## Carry-forward Inquisitor conditions
- **C3 (verbatim from H6):** Post-audit before DNS flip is MANDATORY. The audit IS the launch gate. No exceptions.

## Tasks
- **T1:** `LAUNCH.md` — go/no-go + incident table + rollback plan
- **T2:** DNS flip (Cloudflare → Render custom domain)
- **T3:** Brand rename "Panefree Quotes" → "Panefree Quoting" (31 files)
- **T4:** Email-verified gate on `/checkout`
- **T5:** Tailwind CDN → compiled CSS
- **T6:** UptimeRobot monitors (live URL + backup heartbeat)
- **T7:** Stripe webhook regression test using real `StripeObject` (H6 R1)
- **T8:** Post-launch 30-min active watch + `v1.0.0` tag

## External blockers (track but don't gate task start)
- Postmark approval (questionnaire reply sent 2026-05-13 ~3PM CDT)
- Cookie Policy revision per Inquisitor (Chris is handling in Termly)
- Other legal doc revisions per Inquisitor (if any)
- Inquisitor post-audit verdict on hotfix-6

## Pre-Launch Checklist (Chris-Sprint)
- [x] Phase 1: Accounts (Postmark, Sentry, UptimeRobot, B2)
- [x] Phase 2: DNS auth records (DKIM, SPF, DMARC, Return-Path)
- [x] Phase 3: Stripe Live (keys procured + webhook live + smoke test passed)
- [ ] Phase 4: Legal (Cookie Policy + other Inquisitor revisions in Termly)
- [ ] Phase 5: DNS Flip → Production
