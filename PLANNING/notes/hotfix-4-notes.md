# Hotfix-4 Execution Notes

**Branch:** `hotfix-4` (off master, post-Hotfix-3 merge)
**Executor:** Claude
**Per:** Jade-adopted draft with Inquisitor pre-audit conditions C1 + C2

---

## ⚠️ Mid-sprint scope addition (T0)

The draft Inquisitor pre-audited had **T1-T4** (Sentry, /health, logging audit, ops runbook). **T0 (branding pass) was added after pre-audit** with Chris's explicit authorization on 2026-05-12 because:

1. The panefreequoting.com domain decision landed AFTER H3 merged
2. The new domain + brand name needed to flow into defaults + email copy BEFORE H6's live email smoke test
3. Defending the addition as "remediation of new info" rather than "scope creep" — the underlying need was created by an external decision, not by execution drift

Inquisitor's post-audit will land on a scope she didn't pre-approve. Documented at length here so the audit can verify intent rather than catch a surprise from the git diff. Chris-authorized in the conversation transcript.

T0 itself was purely mechanical: 13 files modified, 39 insertions / 33 deletions, zero functional logic touched, all under "defaults + display strings." Acceptance grep confirms `Window Quoting` is gone from active code (CHANGELOG.md historical entries intentionally preserved).

---

## Decisions, deferrals, and things future-me should know

### T0 — Branding pass

- **Codename "window-quoting" stays everywhere it appears in code paths, log tags, git remote, Stripe metadata.** Only the **user-visible** brand changed. The split keeps internal references stable across the rename.
- **CHANGELOG.md not rewritten.** Historical record of what defaults were at each commit point. Updating those entries would be revisionist; future ops will care more about "what's it set to now" than "what was it 6 months ago."
- **EMAIL_FROM_NAME default = "Panefree Quotes".** Postmark composes `Panefree Quotes <support@panefreequoting.com>` for the From header when both are set.

### T1 — Sentry SDK

- **Init MUST happen before `Flask(__name__)`** so FlaskIntegration's patches are in place when routes register. Tried the post-Flask init and saw silently-missing breadcrumbs.
- **`before_send` does two things**: PII scrub (case-insensitive across data/query_string/headers/cookies) + rate limit. Combined in one hook so we have a single point of "what does Sentry see" rather than two separate filters that can drift.
- **Inquisitor C1 (500/hr rate cap)** implemented as a token bucket per worker. NOT per-DSN across workers — the math is "cap × workers," which is acceptable because the goal is "dashboard stays usable under error storm," not exact quota arithmetic. Multi-worker prod will get a slightly higher effective cap; that's fine for v1.
- **Drop counter logs to stderr, NOT Sentry.** Logging the drop to Sentry would defeat the rate limit. Periodic write to stderr (first drop + every 100th) gives ops visibility without inflation.
- **`/dev/sentry-test`** mirrors `/dev/grant-credits`'s hard-gate pattern (DEV_MODE AND no Stripe key). Verified the 404 path via env-set + config reload.

### T2 — /health

- **Explicitly `@csrf.exempt` AND `@limiter.exempt`.** UptimeRobot + orchestrator probes have no session, no rate-limit budget; either gate would break them.
- **DB check is `SELECT 1`** — sub-millisecond locally. NOT a ping to Stripe / Postmark / Sentry. Those are external dependencies whose failures aren't application failures. The page can render and most user flows work even if Stripe is having an incident.
- **`uptime_s` via `time.monotonic()` snapshot at module load.** Monotonic so NTP jumps don't make it go backwards.
- **`version` reads from `project_root/VERSION`** which the H6 deploy script writes. Falls back to `"dev"` for local runs. Same source as Sentry's `release` tag → errors pin to exact deployed revision.
- **Test client requires `base_url="https://localhost"`** to bypass Talisman's force_https redirect (H2 T4). Production keeps the redirect; tests pretend to be on HTTPS.
- **DB-down live-test on Windows** blocked by SQLite's exclusive file lock. Mocked at the SQLAlchemy boundary in the unit test — same code path, less platform-specific.

### T3 — Logging audit

- **Pre-existing log lines were already structured** (H2 + H3 work adopted the convention consistently). T3 mostly added new happy-path INFO lines: `[REGISTER-SUCCESS]`, `[LOGIN-SUCCESS]`, `[STRIPE-WEBHOOK]`.
- **`[STRIPE-WEBHOOK]` logs event_id**, not the full event payload. Stripe's Dashboard event log is canonical; we just need to cross-reference. Logging the full body would blow up gunicorn logs.
- **Log catalog in DEPLOYMENT.md §9.** 17 tags documented with severity + meaning + suggested response. Sentry alert rules in T4's runbook reference these tags by name — without the catalog, "any error tagged [CREDIT-REFUND-FAILED]" was unverifiable for Inquisitor.

### T4 — Ops runbook + maintenance schedule

- **Inquisitor C2 honored**: email-only alerts, no SMS / Twilio. Sentry mobile app for push.
- **Maintenance schedule** in DEPLOYMENT.md §10.3 as a table — weekly / monthly / quarterly / annually / reactive. `MAINTENANCE_LOG.md` is the append-only artifact; top entry = most recent.
- **On-call rotation is honest.** Solo ops for v1 — Thorn IS the rotation. Phone-on-bedside-table, 4-hour ack SLA, 2-business-day fix for non-critical. Set customer expectations on the contact form.
- **Cadences are defaults, not gospel.** As real signal accumulates (actual error rates, dep churn), revisit at the 3-month and 12-month marks post-launch.

---

## What Chris needs at prod-env time

Two new env vars from H4 (added to `.env.example` under the new "Hotfix-4 — Observability" section):

| Var | Source | Notes |
|---|---|---|
| `SENTRY_DSN` | Sentry project → Client Keys | Unset = no-op (dev/test); set in prod or no error capture |

Plus the H3 set (already documented):
- `POSTMARK_SERVER_TOKEN`, `EMAIL_FROM`, `EMAIL_FROM_NAME`, `ADMIN_EMAIL`

Plus the existing test kill switches (MUST NOT be set in prod): `DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED`.

Chris will get a PowerShell walkthrough when it's deploy time (currently behind H5).

---

## Open items deliberately deferred

- **Real Sentry live smoke** ("deliberate exception via /dev/sentry-test → dashboard receives within 60s"). Chris executes this himself after he plugs `SENTRY_DSN` into prod env — option (b) from execution plan.
- **UptimeRobot monitor setup** — DEPLOYMENT.md §10.1 has the step-by-step; Chris creates the monitor after H6 deploys.
- **Sentry alert rules** — Same pattern. Documented in §10.1; Chris configures via dashboard post-deploy.
- **Per-DSN cross-worker rate limit** (instead of per-worker token bucket). Deferred — multi-worker math is acceptable for v1.
- **Distributed tracing / OpenTelemetry** — explicit out-of-scope per the manifest.
- **Log aggregation service** (Papertrail / Datadog) — Sentry + gunicorn stdout is enough for v1.

---

## Inquisitor conditions — both resolved

- **C1** (Sentry free tier + 500/hr rate cap) — implemented as token-bucket in `_sentry_before_send`. Token state per-process; refill 1 / 7.2s; drained → return None (Sentry drops); periodic stderr log of drop count.
- **C2** (email-only alerts + Sentry mobile app, no SMS/Twilio) — DEPLOYMENT.md §10.1 explicitly states "email-only" and "no SMS / Twilio" with Sentry mobile app as the push channel.

---

## Verification summary

| Check | Result |
|---|---|
| `testing/test_mailer.py` | 9/9 pass |
| `testing/test_sentry_hooks.py` (NEW) | 10/10 pass |
| `testing/test_health.py` (NEW) | 5/5 pass |
| `testing/stress_probe.py` (P1, P5, P6, P8, P9/P10, P11, P12, P13, P14, P15, P16) | All PASS or expected status |
| Locust 30u × 45s | 2387 reqs, 0 failures, p50 16ms / p95 53ms / p99 190ms |
| `grep "Window Quoting"` (excl. CHANGELOG + PLANNING) | 0 matches |
| `grep "windowquoting.com"` (excl. CHANGELOG + PLANNING) | 0 matches |
| `grep "Panefree Quotes"` | 38 matches across code + templates |
| App imports cleanly post-H4 | Yes; `[MAIL] POSTMARK_SERVER_TOKEN unset` error logged (correct — no DSN/token in local env) |
| `/health` returns 200 + JSON in <5ms locally | Yes |
| `/health` returns 503 when DB unreachable (mocked) | Yes |
| `/dev/sentry-test` returns 500 in DEV_MODE | Yes |
| `/dev/sentry-test` returns 404 when STRIPE_SECRET_KEY set | Verified via gate logic |
| Sentry before_send PII scrub on password/customer_*/csrf_token | Yes (unit tests) |
| Sentry rate cap drops events when bucket empty | Yes (unit tests) |
