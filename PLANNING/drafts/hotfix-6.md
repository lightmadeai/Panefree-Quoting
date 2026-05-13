---
label: hotfix-6
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal as sprint-5-ops), Jade (adoption + renumber as hotfix-6 with Inquisitor conditions)
adopted_by: Jade
status: ready
audit_status: pre-approved (conditional)
created: 2026-05-12
depends_on: hotfix-3, hotfix-4, hotfix-5 (all merged + audited)
inquisitor_conditions:
  C1: "Relabeled as hotfix-6 under Stabilize — NOT a new Ops phase. No §13 amendment needed."
  C2: "Live Stripe smoke test uses real card + refund. Test cards only validate test-mode code path; real card validates live pipeline end-to-end."
  C3: "Post-audit before DNS flip is MANDATORY — the audit IS the launch gate. No exceptions."
---

# Hotfix-6 — Production Cutover

## Why

All stabilize-phase blockers are closed (Hotfix-3 user lifecycle,
Hotfix-4 observability, Hotfix-5 backups). Business prerequisites are
in place. This is the cutover itself: the moment the app starts taking
real money from real customers.

## Inquisitor Conditions (RESOLVED)

- **C1:** **Relabeled as hotfix-6 under Stabilize.** NOT a new Ops phase — no §13 amendment needed. The work is stabilize-flavored ("close the last gap, ship"). Adding an Ops phase requires a protocol amendment that's ceremony for a one-time cutover event. If Chris wants Ops as a formal phase for future projects, that's a separate §13 amendment proposal.
- **C2:** **Live Stripe smoke test = real card + refund.** A Stripe test customer with test cards only validates the test-mode code path, which stress_probe already covers. The purpose is to validate the live pipeline: real Stripe keys, real bank account payout, real webhook delivery, real Postmark email. Use Chris's personal card, buy Starter pack ($8.99), verify end-to-end, then refund via Stripe Dashboard. Document the refund transaction ID in notes.
- **C3:** **Post-audit before DNS flip is MANDATORY.** No DNS flip until Inquisitor issues a PASS on the full hotfix-6 sprint. The audit verifies that every prerequisite is checked, every env var is correct, every dev-only escape hatch is absent, and the app can handle real traffic. Skipping this is non-negotiable.

## Prerequisites (must be confirmed by Chris before launch)

- [ ] Stripe live keys generated for this app specifically (separate from Resumeforge)
- [ ] Webhook endpoint configured at `https://<prod-domain>/webhook/stripe` in Stripe Dashboard (live mode)
- [ ] Domain registered, DNS pointed at hosting provider
- [ ] SPF, DKIM, DMARC records added for Postmark-as-sender of `EMAIL_FROM`
- [ ] Privacy Policy + Terms of Service hosted at `/legal/privacy` and `/legal/terms`
- [ ] Business bank account linked in Stripe; payout schedule confirmed
- [ ] Sentry account created, DSN obtained
- [ ] UptimeRobot account created, /health monitor + backup heartbeat configured
- [ ] Backup destination (B2 / S3 bucket) provisioned + credentials ready

## Goals

- App live at production domain over HTTPS
- One real paid transaction completed end-to-end
- All monitoring + alerting confirmed firing
- Documented rollback path

## Tasks

### T1: Production WSGI + reverse proxy + ProxyFix
**touches:** new `gunicorn.conf.py`, hosting config, `app.py` for ProxyFix
**acceptance:**
- Gunicorn config: 2-4 workers (start with 2), 30s timeout, access log to stdout.
- `werkzeug.middleware.proxy_fix.ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)` wired in `app.py`.
- TLS termination at the proxy. Cert auto-renewal verified.
- HTTP → HTTPS redirect verified via curl.
- Talisman's `force_https` works correctly with the proxy (no redirect loops).

### T2: Production environment variables
**touches:** hosting provider's secrets store (NOT a file in the repo)
**acceptance:**
- All required env vars set in prod (from `.env.example`):
  - `SRE_SECRET_KEY` — freshly generated (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
  - `STRIPE_SECRET_KEY` = `sk_live_...` (this app's key)
  - `STRIPE_PUBLISHABLE_KEY` = `pk_live_...`
  - `STRIPE_WEBHOOK_SECRET` = `whsec_...` from the live endpoint
  - `APP_BASE_URL` = the real https domain
  - `POSTMARK_SERVER_TOKEN`, `EMAIL_FROM`, `EMAIL_FROM_NAME`, `ADMIN_EMAIL`
  - `SENTRY_DSN`
  - `BACKUP_DESTINATION` + cloud auth (B2 / AWS keys)
  - `SUPPORT_EMAIL`
- Confirmed NOT set in prod:
  - `DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED`
- Pre-flight smoke (DEPLOYMENT.md §2.1-2.9) passes before DNS flip.

### T3: Flask-Limiter Redis storage (gated on multi-worker)
**touches:** `app.py` Limiter() config, env, hosting Redis provisioning
**acceptance:**
- IF gunicorn runs ≥2 workers: provision Redis (managed instance, cheapest tier), set `REDIS_URL` env, update Limiter `storage_uri` to `os.environ.get("REDIS_URL", "memory://")`.
- IF single-worker (acceptable for low-traffic launch): document the deferral. Single-worker means downtime during deploys >5s. Tradeoff acceptable for v1.

### T4: Live Stripe smoke test
**touches:** prod only — no code change
**acceptance:**
- **Real card + refund (Inquisitor C2):** Buy Starter pack ($8.99) with Chris's personal card. Checkout completes, webhook fires, credits land, `/api/credits` reflects new balance.
- Buy Annual subscription ($179): webhook fires, `subscription_status` = active, reserve bypass works.
- Refund both test charges via Stripe Dashboard; confirm refund webhook received. Document refund transaction IDs in notes.
- Stripe events tab inspected — every webhook returned 2xx.

### T5: Launch checklist + watch window + rollback plan
**touches:** new `LAUNCH.md`
**acceptance:**
- `LAUNCH.md` go/no-go checklist:
  - Final pre-flight smoke run (DEPLOYMENT.md §2.1-2.9 all green)
  - DNS cut-over
  - First-customer-can-sign-up smoke (real new account)
  - 30-minute active watch with Sentry, /health, gunicorn logs, Stripe Dashboard
- "If X happens, do Y" incident table
- Rollback plan: known-good deploy tag + redeploy procedure + user notification plan
- `master` tagged `v1.0.0` after successful launch
- **Post-audit before DNS flip (Inquisitor C3):** Inquisitor audits the full sprint. PASS required before DNS flip.

## Out of scope

- Marketing site / landing page (separate project)
- Sales funnel / signup analytics
- Customer support ticketing — email + manual triage for v1
- Geographic distribution / CDN for static assets
- A/B testing infrastructure

## Definition of done

- All prerequisites checked
- T1-T5 acceptance criteria met
- Inquisitor post-audit verdict: PASS
- DNS flipped; app live at production domain over HTTPS
- One real paid transaction completed end-to-end
- Sentry, UptimeRobot, backups all firing on schedule
- `LAUNCH.md` committed
- `master` tagged `v1.0.0`
- `notes/hotfix-6-notes.md` captures design decisions and launch-day timeline