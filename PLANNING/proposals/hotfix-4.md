---
label: hotfix-4
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal for Jade, 2026-05-12)
status: draft
audit_status: draft
created: 2026-05-12
depends_on: hotfix-3 (mailer.py — admin alerts on failures route through it)
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
- Integration verified: deliberate `raise Exception("sentry test")` in a
  dev-only `/dev/sentry-test` route (gated identically to
  `/dev/grant-credits`) surfaces in the dashboard within 60 seconds.

### T2: Health check endpoint
**touches:** `app.py`, DEPLOYMENT.md
**acceptance:**
- New `/health` route (no auth, no rate limit) returns JSON:
  `{"status": "ok", "db": "ok", "version": "<git-sha-or-dev>", "uptime_s": N}`.
- Reads the git SHA at boot from a `VERSION` file written by the deploy
  script (Sprint 9 wires this); falls back to `"dev"` if missing.
- DB check is a `SELECT 1`; failure returns 503 with
  `{"status": "degraded", "db": "fail"}`.
- Response time target: <50ms p95. Does NOT hit Stripe / Postmark / other
  external services — those failures aren't application failures and the
  page can still load + most flows still work.
- Talisman / CSRF protections on this route: `@csrf.exempt` (no session),
  Talisman default headers fine.

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
  webhook events received. These give a forensic trail without Sentry
  needing to ingest happy-path events.
- DEPLOYMENT.md gets a "Log catalog" section listing every structured
  tag with severity + meaning + recommended response.

### T4: Operations runbook + maintenance schedule
**touches:** DEPLOYMENT.md only — no code changes
**acceptance:**
- New "Operations" section covers:
  - **UptimeRobot setup**: 5-min ping on /health, alert email + (optional)
    SMS. Step-by-step setup with screenshots-or-text walkthrough.
  - **Sentry alert rules** (recommended):
    - Any unresolved error >5 occurrences/hour
    - Any error tagged `[CREDIT-REFUND-FAILED]` or `[STRIPE-*]` >1/hour
    - Page p95 latency >2s for 15 consecutive min
  - **Alert → response playbook (reactive)**: for each common alert, the
    "investigate → mitigate → fix" sequence. Examples:
    - `[CREDIT-REFUND-FAILED]` → tail logs, find user_id, manually
      credit via sqlite3, file fix sprint
    - /health 503 → check disk, check DB lock, restart gunicorn,
      if not recovered: failover (no failover for v1 = call it)
    - Stripe webhook 4xx rate spike → check `STRIPE_WEBHOOK_SECRET`,
      check Stripe Dashboard event log
  - **Maintenance schedule (proactive)** — calendar-driven, not
    incident-driven. Documented as a recurring-task table with frequency,
    task, expected duration, and Sentry/log/Stripe Dashboard URL where
    applicable:

    | Cadence | Task | Time |
    |---|---|---|
    | Weekly (every Monday) | Skim Sentry unresolved errors; skim gunicorn access log for 5xx; check Stripe Dashboard for failed payments / disputes; glance at signup + quote volume | 15-30 min |
    | Monthly (1st of month) | Run `pip-audit --requirement requirements.txt --strict`. Bump any flagged deps, re-run stress_probe + locust, redeploy. Review Sentry quota usage. | 1-2 hours |
    | Quarterly (Jan/Apr/Jul/Oct 1st) | Full re-run of stress_probe + locust + pip-audit. Execute one full backup restore drill (see Hotfix-5). Read Stripe Dashboard tax / payout summary. Re-read DEPLOYMENT.md for stale instructions. | 2-4 hours |
    | Annually (each January) | Major-version upgrades (Flask N → N+1, Python 3.x → 3.x+1). TLS cert renewal verification (auto-renew should handle, but verify). Re-run the full pre-launch security review. Archive prior year's backups beyond retention to cold storage if desired. | 1 day |
    | Reactive | Customer reports a bug → triage same day → fix within the week. Security or billing reports → same-day fix, no exceptions. | Variable |

  - **Maintenance log**: a `MAINTENANCE_LOG.md` file in the repo root,
    appended on each scheduled maintenance pass with date + what was
    done + anything anomalous. Single source of truth for "when did we
    last check X." Skipping entries = visible gap.
  - **Backup verification cadence**: covered in the quarterly row above;
    Hotfix-5 owns the actual restore-drill procedure that the quarterly
    task references.
  - **On-call rotation**: one-person ops for v1 — Thorn IS the rotation.
    Document phone-on-bedside-table expectation honestly. Note the
    realistic SLA for a solo operator: acknowledged within 4 business
    hours, fixed within 2 business days for non-billing/non-security
    issues. Set customer expectations on the contact form accordingly.

## Out of scope

- Distributed tracing / OpenTelemetry (overkill for one process)
- Log aggregation service (Papertrail / Datadog) — Sentry covers errors;
  gunicorn logs to file is enough for v1; revisit at 500+ MAU.
- Session replay tools (Fullstory / Hotjar) — privacy implications,
  not needed for v1.
- Real-time dashboards (Grafana / Datadog dashboards) — overkill.
- PagerDuty / Opsgenie integration — solo ops, email + SMS sufficient.

## Open questions for Jade / Inquisitor

- Is the Sentry free tier (5k errors/month) sufficient for v1? If a
  Day-1 bug causes a loop, we could exhaust it fast. Proposal: accept
  the risk; budget upgrade if it happens.
- Should `/health` be on a separate, non-Talisman'd route (some hosting
  providers' health checks don't follow redirects)? Proposal: leave on
  the main app; force_https redirects are 301s and health checkers
  generally follow.
- Open question for Thorn: do you want SMS alerts on critical errors,
  or email-only for v1? (SMS adds ~$1/mo Twilio cost.)

## Definition of done

- Sentry receives a test error within 60s of deliberate trigger
- `/health` returns 200 + JSON in <50ms; returns 503 in DB-down scenario
  (verified via temporarily renaming `sovereign.db`)
- All `app.logger.*` lines in `app.py` audited; log catalog committed to
  DEPLOYMENT.md
- Operations runbook + maintenance schedule + initial empty
  `MAINTENANCE_LOG.md` committed
- Commits on `hotfix-4` branch
- `notes/hotfix-4-notes.md` captures any design decisions
