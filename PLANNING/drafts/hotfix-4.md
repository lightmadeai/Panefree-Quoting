---
label: hotfix-4
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal), Jade (adoption with Inquisitor conditions)
adopted_by: Jade
status: ready
audit_status: pre-approved (conditional)
created: 2026-05-12
depends_on: hotfix-3 (mailer.py — admin alerts on failures route through it)
inquisitor_conditions:
  C1: "Sentry free tier accepted — add before_send rate limiter cap at 500 errors/hour to prevent dashboard burnout"
  C2: "Email-only alerts for v1 + Sentry mobile app (free). No SMS/Twilio integration."
---

# Hotfix-4 — Observability: Sentry + Health Check + Ops Runbook

## Why

Currently the only way to find out about a production error is for a
customer to email support. By then they've already bounced. Post-launch
operations need (1) automatic exception capture, (2) automated uptime
monitoring, and (3) a documented runbook so the operator (Thorn,
solo-ops for v1) knows how to respond when alerts fire.

## Goals

- Every uncaught exception in production surfaces in Sentry within seconds
- /health endpoint enables external uptime monitoring (UptimeRobot)
- All warning/error log lines are structured, searchable, and documented
- The operator has a written playbook for the most likely Day-1 incidents

## Inquisitor Conditions (RESOLVED)

- **C1:** Sentry free tier (5k errors/month) accepted with one safeguard: add a `before_send` rate limiter that caps Sentry to 500 errors/hour. One line of code. If a Day-1 bug causes a loop, the dashboard stays useful. If the free tier is consistently hit, upgrade to the $26/mo plan (50k errors).
- **C2:** **Email-only alerts for v1.** UptimeRobot email + Sentry email is sufficient for solo ops. SMS adds Twilio cost + integration complexity. For mobile push notifications, use the Sentry mobile app (free).

## Tasks

### T1: Sentry SDK integration
**touches:** `app.py`, `requirements.txt`, `.env.example`, DEPLOYMENT.md
**acceptance:**
- `sentry-sdk[flask]` added to `requirements.txt` (pinned via `~=`).
- `sentry_sdk.init(dsn=os.environ.get("SENTRY_DSN"), ...)` at the top
  of `app.py` (before app creation). Guarded — if `SENTRY_DSN` unset,
  Sentry is a no-op (dev/test runs don't pollute the dashboard).
- `traces_sample_rate=0.1` (10% performance sampling — Sentry free-tier
  budget-friendly; bump if needed post-launch).
- `release` set to the same git SHA exposed via `/health` (T2) so errors
  pin to the exact deployed revision.
- `before_send` hook scrubs known PII fields from request context: any
  field named `password`, `csrf_token`, `customer_email`, `customer_phone`,
  `customer_address` is replaced with `"[scrubbed]"` before transmit.
- **Rate limiter cap (Inquisitor C1):** `before_send` also implements a
  500 errors/hour cap. If the hourly bucket is exceeded, drop the event
  and log `[SENTRY-RATE-LIMITED]`. Keeps the dashboard useful under error storms.
- Integration verified: deliberate `raise Exception("sentry test")` in a
  dev-only `/dev/sentry-test` route (gated identically to
  `/dev/grant-credits`) surfaces in the dashboard within 60 seconds.

### T2: Health check endpoint
**touches:** `app.py`, DEPLOYMENT.md
**acceptance:**
- New `/health` route (no auth, no rate limit) returns JSON:
  `{"status": "ok", "db": "ok", "version": "<git-sha-or-dev>", "uptime_s": N}`.
- Reads the git SHA at boot from a `VERSION` file written by the deploy
  script; falls back to `"dev"` if missing.
- DB check is a `SELECT 1`; failure returns 503 with
  `{"status": "degraded", "db": "fail"}`.
- Response time target: <50ms p95. Does NOT hit Stripe / Postmark / other
  external services.
- `@csrf.exempt` (no session), Talisman default headers fine.

### T3: Structured logging audit
**touches:** `app.py` (all `app.logger.*` call sites)
**acceptance:**
- Every `app.logger.warning` and `app.logger.error` call includes:
  - A structured tag in brackets (e.g. `[CREDIT-REFUND-FAILED]`) so log
    searches are deterministic
  - `user_id` when available
  - The triggering Stripe ID / quote ID / etc. when applicable
- Audit existing log lines; bring stragglers up to the standard.
- New `app.logger.info` for: successful login, successful registration,
  successful Stripe checkout, account deletion (already in H3),
  webhook events received.
- DEPLOYMENT.md gets a "Log catalog" section listing every structured
  tag with severity + meaning + recommended response.

### T4: Operations runbook + maintenance schedule
**touches:** DEPLOYMENT.md only — no code changes
**acceptance:**
- New "Operations" section covers:
  - **UptimeRobot setup**: 5-min ping on /health, alert email. Step-by-step walkthrough.
  - **Sentry alert rules** (recommended):
    - Any unresolved error >5 occurrences/hour
    - Any error tagged `[CREDIT-REFUND-FAILED]` or `[STRIPE-*]` >1/hour
    - Page p95 latency >2s for 15 consecutive min
  - **Alert → response playbook (reactive)**: for each common alert, the
    "investigate → mitigate → fix" sequence.
  - **Maintenance schedule (proactive)** — documented as a recurring-task table:
    | Cadence | Task | Time |
    |---|---|---|
    | Weekly (Monday) | Skim Sentry unresolved errors; gunicorn 5xx; Stripe Dashboard failed payments; signup + quote volume | 15-30 min |
    | Monthly (1st) | `pip-audit --strict`; bump flagged deps; re-run stress_probe + locust; review Sentry quota | 1-2 hours |
    | Quarterly (Jan/Apr/Jul/Oct 1st) | Full re-run stress_probe + locust + pip-audit; one backup restore drill (H5); review Stripe tax/payout; re-read DEPLOYMENT.md for stale instructions | 2-4 hours |
    | Annually (January) | Major-version upgrades; TLS cert verification; full security review; archive old backups | 1 day |
    | Reactive | Customer bug → triage same day; security/billing → same-day fix | Variable |
  - **Maintenance log**: `MAINTENANCE_LOG.md` in repo root, appended on each pass.
  - **On-call rotation**: One-person ops for v1 — Thorn IS the rotation.
    Realistic SLA: acknowledged within 4 business hours, fixed within 2
    business days for non-billing/non-security issues.

## Out of scope

- Distributed tracing / OpenTelemetry (overkill for one process)
- Log aggregation service (Papertrail / Datadog) — Sentry covers errors;
  gunicorn logs to file is enough for v1
- Session replay tools (Fullstory / Hotjar) — privacy implications
- Real-time dashboards (Grafana / Datadog dashboards) — overkill
- PagerDuty / Opsgenie integration — solo ops, email + Sentry app sufficient

## Definition of done

- Sentry receives a test error within 60s of deliberate trigger
- `/health` returns 200 + JSON in <50ms; returns 503 in DB-down scenario
- All `app.logger.*` lines in `app.py` audited; log catalog committed to DEPLOYMENT.md
- Operations runbook + maintenance schedule + initial empty `MAINTENANCE_LOG.md` committed
- Commits on `hotfix-4` branch
- `notes/hotfix-4-notes.md` captures any design decisions