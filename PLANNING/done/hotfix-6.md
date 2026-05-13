---
label: hotfix-6
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal as sprint-5-ops), Jade (adoption + renumber as hotfix-6 with Inquisitor conditions)
adopted_by: Jade
status: done
completed: 2026-05-13
audit_status: pending
audit_note: "T1–T4 landed including the unplanned but Chris-authorized additions (GitHub repo creation, Render Disk for SQLite persistence, CSP form-action fix, two Stripe webhook handler bug fixes). T5 (LAUNCH.md) + DNS flip + v1.0.0 tag rolled to hotfix-7 because Postmark approval, Cookie Policy revision, and Inquisitor post-audit all multi-day external blockers. Live billing pipeline validated end-to-end with real card + refund per Inquisitor C2. Inquisitor C3 (mandatory post-audit before DNS flip) transfers verbatim to hotfix-7."
created: 2026-05-12
depends_on: hotfix-5 (DONE, PASS)
next_up: hotfix-7
---

# Hotfix-6 — Production Cutover (closed)

**Full draft:** `PLANNING/drafts/hotfix-6.md`
**Notes:** `PLANNING/notes/hotfix-6-notes.md`
**Next sprint:** `PLANNING/proposals/hotfix-7.md` (awaiting Jade adoption)

## Pipeline Status
- **Hotfix-2:** ✅ DONE, PASS
- **Hotfix-3:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-4:** ✅ DONE, PASS (3 non-blocking remarks)
- **Hotfix-5:** ✅ DONE, PASS (4 non-blocking remarks)
- **Hotfix-6:** ✅ DONE (T1–T4) — awaiting Inquisitor post-audit verdict
- **Hotfix-7:** ⏳ PROPOSED — actual launch event + deferred polish

## What landed
- T1: Production WSGI (gunicorn) + ProxyFix + legal routes
- T2: Production env vars on Render (Stripe live, Postmark, Sentry, B2, Sentry DSN)
- T3: Single-worker gunicorn (Redis deferred — see notes)
- T4: Real-card live Stripe smoke test (both tiers, both refunded, sub cancelled)
- **Plus** five Chris-authorized scope additions documented in notes:
  - GitHub repo creation + first push
  - Render Disk for SQLite persistence (`DATABASE_PATH` env var honored)
  - CSP `form-action` fix for Stripe Checkout redirect
  - Webhook handler fix: `event["id"]` not `event.get("id")`
  - Webhook handler fix: convert StripeObject → dict at dispatch (durable)

## What rolled to hotfix-7
- T5 (LAUNCH.md + go/no-go + rollback plan)
- DNS flip (Cloudflare → Render custom domain)
- `v1.0.0` tag
- Cookie Policy revision (Termly, Chris-driven)
- Other legal doc updates per Inquisitor
- Brand rename: "Panefree Quotes" → "Panefree Quoting" (31 files)
- Email-verified gate on `/checkout` (UX gap discovered in smoke test)
- Tailwind CDN → compiled CSS
- UptimeRobot monitor setup
- Stripe webhook regression test using real `StripeObject` (H6 R1)

## Inquisitor pre-audit conditions
- **C1** (relabel as hotfix-6 under Stabilize): ✅ honored
- **C2** (real card + refund, not Stripe test cards): ✅ honored fully
- **C3** (mandatory post-audit before DNS flip): ✅ **transfers verbatim to hotfix-7** — audit IS the launch gate, no exception
