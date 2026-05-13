---
label: sprint-5-ops    # provisional — Jade may renumber as hotfix-6
project: window-quoting
phase: ops             # NEW phase per §13 — see open question below
drafted_by: Claude (proposal for Jade, 2026-05-12)
status: draft
audit_status: draft
created: 2026-05-12
depends_on: hotfix-3, hotfix-4, hotfix-5 (all merged + audited)
---

# Sprint 5 (Ops) — Production Cutover

## Why

All stabilize-phase blockers are closed (Hotfix-3 user lifecycle,
Hotfix-4 observability, Hotfix-5 backups). Business prerequisites are
in place (domain, legal pages, Stripe live keys generated for this app,
hosting provider chosen). This sprint is the cutover itself: the moment
the app starts taking real money from real customers.

## Prerequisites (must be confirmed by Thorn before launch)

- [ ] Stripe live keys generated for **this app specifically** (separate
      from Resumeforge — restricted-key set scoped to window-quoting's
      webhook endpoint).
- [ ] Webhook endpoint configured at `https://<prod-domain>/webhook/stripe`
      in Stripe Dashboard (live mode); `whsec_...` recorded.
- [ ] Domain registered, DNS pointed at hosting provider.
- [ ] SPF, DKIM, DMARC records added for Postmark-as-sender of `EMAIL_FROM`.
- [ ] Privacy Policy + Terms of Service hosted at `/legal/privacy` and
      `/legal/terms` (either committed as static Jinja templates in this
      repo OR linked from the footer to an external service like Termly).
- [ ] Business bank account linked in Stripe; payout schedule confirmed.
- [ ] Sentry account created, DSN obtained.
- [ ] UptimeRobot account created, /health monitor + backup heartbeat
      monitor configured.
- [ ] Backup destination (B2 / S3 bucket) provisioned + credentials ready.

Until every prerequisite is checked, this sprint is `draft` — it does
NOT promote to `ready`.

## Goals

- App live at production domain over HTTPS
- One real paid transaction completed end-to-end
- All monitoring + alerting confirmed firing
- Documented rollback path

## Tasks

### T1: Production WSGI + reverse proxy + ProxyFix
**touches:** new `gunicorn.conf.py`, hosting config (`Procfile` / `render.yaml`
  / nginx.conf depending on host), `app.py` for ProxyFix middleware
**acceptance:**
- Gunicorn config: 2-4 workers (start with 2), 30s timeout, access log
  to stdout (so the hosting provider's log shipper ingests).
- `werkzeug.middleware.proxy_fix.ProxyFix(app.wsgi_app, x_for=1, x_proto=1,
  x_host=1, x_port=1)` wired in `app.py`. Without this, Flask-Limiter
  buckets every request under the proxy's single IP and rate limits
  globally.
- TLS termination at the proxy. Cert auto-renewal verified (Let's Encrypt
  via Caddy / Render-managed / etc., depending on host).
- HTTP → HTTPS redirect verified via curl.
- Talisman's `force_https` works correctly in concert with the proxy
  (verified — no redirect loops).

### T2: Production environment variables
**touches:** hosting provider's secrets store (NOT a file in the repo)
**acceptance:**
- All required env vars set in prod (from `.env.example`):
  - `SRE_SECRET_KEY` — freshly generated, NEVER the dev default
    (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
  - `STRIPE_SECRET_KEY` = `sk_live_...` (this app's key, not Resumeforge's)
  - `STRIPE_PUBLISHABLE_KEY` = `pk_live_...`
  - `STRIPE_WEBHOOK_SECRET` = `whsec_...` from the live endpoint
  - `APP_BASE_URL` = the real https domain (no trailing slash)
  - `POSTMARK_SERVER_TOKEN`, `EMAIL_FROM`, `EMAIL_FROM_NAME`, `ADMIN_EMAIL`
  - `SENTRY_DSN`
  - `BACKUP_DESTINATION` + cloud auth (B2 / AWS keys)
  - `SUPPORT_EMAIL`
- Confirmed NOT set in prod (explicit grep against the live env):
  - `DEV_MODE`
  - `WTF_CSRF_DISABLED`
  - `RATELIMIT_DISABLED`
  - `MAIL_DISABLED`
- Pre-flight smoke (DEPLOYMENT.md §2.1, 2.2, 2.8, 2.9) passes against
  production env before flipping DNS / making the app reachable.

### T3: Flask-Limiter Redis storage (gated on multi-worker)
**touches:** `app.py` Limiter() config, env, hosting Redis provisioning
**acceptance:**
- IF gunicorn runs ≥2 workers: provision Redis (managed instance,
  cheapest tier — Render's $7/mo Redis, Upstash free tier, etc.), set
  `REDIS_URL` env, update Limiter `storage_uri` to
  `os.environ.get("REDIS_URL", "memory://")`. Memory-default keeps dev
  working unchanged.
- IF single-worker (acceptable for low-traffic launch): document the
  deferral here and revisit when traffic justifies. Note: single-worker
  means downtime during any deploy that takes >5s. Tradeoff acceptable
  for v1.
- Verified by hitting `/login` 11x in rapid succession against prod and
  confirming the 11th request returns 429 regardless of which worker
  picked it up (Redis storage shares state across workers; memory does
  not).

### T4: Live Stripe smoke test
**touches:** prod only — no code change
**acceptance:**
- One real card purchase of the Starter pack ($8.99) goes through
  end-to-end: Checkout completes, `checkout.session.completed` webhook
  fires, credits land, `/api/credits` reflects the new balance.
- One real subscription purchase of Annual ($179) completes: webhook
  fires, `subscription_status` = active, `subscription_current_period_end`
  set, reserve bypass works on the next `/generate`.
- Refund the test charges via Stripe Dashboard; confirm refund webhook
  is received (current code doesn't process it specially; note for a
  future sprint if customer support pattern demands).
- Stripe events tab inspected — every webhook returned 2xx.

### T5: Launch checklist + watch window + rollback plan
**touches:** new `LAUNCH.md`, possibly `RELEASE_NOTES.md`
**acceptance:**
- `LAUNCH.md` contains a go/no-go checklist that Thorn executes on
  launch day:
  - Final pre-flight smoke run (DEPLOYMENT.md §2.1-2.9 all green)
  - DNS cut-over (or "flip the toggle" on the PaaS)
  - First-customer-can-sign-up smoke (real new account)
  - 30-minute active watch with Sentry, /health, and gunicorn logs
    open in three windows + Stripe Dashboard tab open
- "If X happens, do Y" table for the most likely Day-1 incidents:
  - Verification email not arriving → check Postmark dashboard,
    check SPF/DKIM/DMARC, check spam folder
  - Stripe webhook silently failing → check Stripe events tab,
    verify whsec env, look for `[STRIPE-*]` log lines in Sentry
  - /health flapping → check disk, check DB lock, restart workers
- Rollback plan:
  - Which deploy is "known good"
  - How to revert (git tag + redeploy)
  - How to notify already-signed-up users if a rollback loses data
    (admin SQL + targeted email via Postmark)
- `master` tagged `v1.0.0` after successful launch.

## Out of scope

- Marketing site / landing page (separate project)
- Sales funnel / signup analytics (separate project)
- Customer support ticketing — email + manual triage for v1
- Geographic distribution / CDN for static assets (premature)
- A/B testing infrastructure (premature)

## Open questions for Jade / Inquisitor

- §13 currently defines only Build and Stabilize phases. Either:
  a) Jade proposes a §13 amendment via `drafts/protocol-change-N.md`
     adding an Ops phase; Inquisitor approves; this sprint runs under
     the new phase tag.
  b) Relabel this `hotfix-6` and run it as the final Stabilize hotfix.
  Claude leans (b) — lower ceremony, work is stabilize-flavored
  ("close the last gap, ship"). Final call: Inquisitor.
- Should T4 (live Stripe smoke) use Thorn's personal card and then
  refund, or set up a Stripe test customer with a real test card?
  Proposal: real card + refund, since the goal is to verify the full
  end-to-end pipeline including bank-account payout setup.
- Should Sprint 5 wait for an Inquisitor post-audit before flipping
  DNS, or is execution + Thorn-initiated flip sufficient? Proposal:
  post-audit must happen before DNS flip — the audit IS the launch
  gate.

## Definition of done

- All prerequisites checked
- T1-T5 acceptance criteria met
- Inquisitor post-audit verdict: PASS
- DNS flipped; app live at production domain over HTTPS
- One real paid transaction completed end-to-end
- Sentry, UptimeRobot, backups all firing on schedule
- `LAUNCH.md` committed
- `master` tagged `v1.0.0`
- `notes/sprint-5-ops-notes.md` (or `hotfix-6-notes.md`) captures any
  design decisions and the launch-day timeline
