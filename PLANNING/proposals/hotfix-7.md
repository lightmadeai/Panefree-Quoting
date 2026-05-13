---
label: hotfix-7
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal — awaiting Jade adoption)
adopted_by: pending
status: proposed
audit_status: pre-audit-pending
created: 2026-05-13
depends_on: hotfix-6 (DONE, awaiting Inquisitor post-audit verdict)
next_up: production launch + post-launch monitoring
inquisitor_conditions_carried_forward:
  C3_from_H6: "Post-audit before DNS flip is MANDATORY. The audit IS the launch gate. No DNS flip until Inquisitor issues a PASS on the full hotfix-7 sprint."
---

# Hotfix-7 — Launch Execution + Deferred Polish

## Why

Hotfix-6 enabled the production cutover machinery (live Stripe pipeline, persistent DB, CSP rules for payment redirects, webhook handler reliability). External blockers (Postmark approval, Inquisitor cookie policy audit, Inquisitor H6 post-audit) prevented the actual launch event from landing in H6.

Hotfix-7 is the launch itself plus polish items deferred during H6 execution.

## Inquisitor conditions (carried forward from H6)

**C3 (carried verbatim):** Post-audit before DNS flip is MANDATORY. No DNS flip without Inquisitor PASS verdict on this sprint.

## Prerequisites (must be confirmed by Chris before launch)

- [ ] Postmark approval received (questionnaire reply sent 2026-05-13 ~3PM CDT; SLA 1-2 days)
- [ ] Cookie Policy revision approved by Inquisitor + republished by Chris via Termly
- [ ] Privacy Policy + Terms of Service updates per Inquisitor (if any) republished via Termly
- [ ] Cloudflare DNS access confirmed (you own `panefreequoting.com`, can edit records)
- [ ] Stripe webhook can be re-pointed at `panefreequoting.com` (or the existing endpoint at `panefree-quoting.onrender.com` can be left in place if DNS flip uses a redirect strategy)

## Goals

- App reachable at `https://panefreequoting.com` over HTTPS with a valid TLS cert
- Brand-display strings ("Panefree Quotes" → "Panefree Quoting") consistent everywhere
- Email-verified gate at the earliest payment-flow entry point (UX repair)
- `LAUNCH.md` written and used during the actual launch window
- 30-minute active watch window completed post-DNS-flip
- `v1.0.0` tag applied on `master` after successful launch

## Tasks

### T1: LAUNCH.md — go/no-go checklist + incident table + rollback plan
**touches:** new `LAUNCH.md` at repo root
**acceptance:**
- Go/no-go checklist:
  - Final pre-flight smoke per DEPLOYMENT.md §2.1-2.9 all green
  - DNS records confirmed correct in Cloudflare
  - Stripe live webhook URL matches the production domain
  - All env vars confirmed set on Render
  - First-customer-can-sign-up smoke (real new account on the new domain)
  - 30-minute active watch with Sentry, /health, gunicorn logs, Stripe Dashboard
- Incident response table: "if X happens, do Y" for at least: webhook 5xx, signup 5xx, Stripe payment 5xx, email send fail, /health flapping
- Rollback plan: known-good deploy SHA + Render redeploy procedure + user-notification draft
- `v1.0.0` tag procedure
- Documents that Inquisitor C3 has been satisfied before this checklist runs

### T2: DNS flip — Cloudflare → Render custom domain
**touches:** Cloudflare DNS (zone for `panefreequoting.com`), Render Custom Domains tab
**acceptance:**
- `panefreequoting.com` added in Render Settings → Custom Domains
- DNS records added per Render's instructions (A record on apex via Cloudflare flattening, CNAME on `www`)
- Cloudflare proxy (orange cloud) decision documented — likely DNS-only initially to avoid double-TLS / cert provisioning conflicts with Render's Let's Encrypt
- Render shows ✅ Verified + active cert on both `panefreequoting.com` and `www.panefreequoting.com`
- `APP_BASE_URL` env var updated from `https://panefree-quoting.onrender.com` to `https://panefreequoting.com`
- Stripe webhook endpoint URL updated to `https://panefreequoting.com/webhook/stripe` (existing `whsec_…` stays valid)
- Curl test confirms `https://panefreequoting.com/health` returns 200 from outside

### T3: Brand rename — "Panefree Quotes" → "Panefree Quoting"
**touches:** 31 files across templates, email bodies, error pages, config defaults, plus `EMAIL_FROM_NAME` env on Render
**acceptance:**
- Single sweep find/replace
- Acceptance grep: `git grep -F "Panefree Quotes"` returns only CHANGELOG / historical-record entries
- `EMAIL_FROM_NAME` env var on Render updated to `Panefree Quoting`
- One smoke send post-rename to verify the From-header composition
- No functional logic touched

### T4: Email-verified gate on `/checkout`
**touches:** `app.py` `/checkout` route
**acceptance:**
- Same gate pattern as `/generate` (app.py:1496): if `not user.email_verified`, redirect to `/account` with flash message "Verify your email before purchasing credits"
- Subscribers NOT exempt (consistent with H4 reasoning — stolen-card subscription abuse vector)
- Fires before any Stripe Checkout session is created (no orphan sessions in Stripe Dashboard)
- Tested manually: unverified user clicks Buy → sees flash, not Stripe page

### T5: Tailwind CDN → compiled CSS
**touches:** new `package.json`, `tailwind.config.js`, build pipeline, templates that reference Tailwind
**acceptance:**
- Tailwind CLI installed as dev dependency
- Source CSS file scanned against templates → compiled to `static/css/tailwind.css`
- Templates updated from `<script src="https://cdn.tailwindcss.com">` to `<link rel="stylesheet" href="{{ url_for('static', filename='css/tailwind.css') }}">`
- Render build command updated to run Tailwind build before gunicorn starts
- CSP `script-src` no longer needs `cdn.tailwindcss.com` (tighter CSP — bonus)
- Browser console no longer shows the Tailwind dev-mode warning

### T6: UptimeRobot monitors
**touches:** UptimeRobot dashboard (external; doc the configuration here)
**acceptance:**
- Monitor: `https://panefreequoting.com/health` — 5-min interval, alert on 2 consecutive failures, email to `lightmadeai@gmail.com`
- Backup heartbeat URL created; `BACKUP_HEARTBEAT_URL` env var set on Render; scripts/backup.py pings it on success
- Alert routes documented in DEPLOYMENT.md §10 (or similar ops runbook section)

### T7: Stripe webhook regression test (H6 R1)
**touches:** `testing/test_stripe_webhook.py` (likely new file)
**acceptance:**
- Test constructs a real `stripe.Event` (or `StripeObject`) using `stripe.Event.construct_from(...)` with a fixture payload
- Test posts to `/webhook/stripe` with the matching Stripe-Signature header
- Test verifies the handler returns 200 and credits are applied
- Test guarantees the StripeObject `.get()` bug class would be caught by CI before reaching production
- Coverage: at minimum `checkout.session.completed` (payment mode) and `customer.subscription.deleted`

### T8: Post-launch active watch + v1.0.0 tag
**touches:** ops only — no code
**acceptance:**
- 30-min watch window starting at DNS flip moment
- Sentry observed: no new error issue types after first real-customer signup
- Stripe Dashboard observed: first real customer transaction (if any) completes cleanly
- `/health` polled every 1 minute for the watch window, all 200
- gunicorn logs observed for unexpected tracebacks
- `git tag v1.0.0` on `master`, pushed to origin
- Watch window summary appended to `notes/hotfix-7-notes.md`

## Out of scope

- Multi-worker gunicorn + Redis-backed Flask-Limiter (post-launch when traffic justifies)
- Marketing site / landing page work
- Customer-support tooling (email-only for v1)
- Analytics integration
- CDN for static assets (Cloudflare proxy may serve this if turned on later)

## Definition of done

- All prerequisites checked
- T1–T8 acceptance met
- Inquisitor post-audit: PASS
- App live at `https://panefreequoting.com` over HTTPS
- One real customer flow exercised on the production domain (Chris's test signup with a non-account email after Postmark approval)
- Sentry, UptimeRobot, backups all firing on schedule
- `LAUNCH.md` committed
- `master` tagged `v1.0.0` and pushed
- `notes/hotfix-7-notes.md` captures the launch-day timeline and any incidents
