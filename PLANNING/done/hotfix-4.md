---
label: hotfix-4
project: window-quoting
phase: stabilize
status: done
created: 2026-05-12
completed: 2026-05-12
audit_status: pending
audit_note: "All 5 tasks landed (T0 added mid-sprint with Chris's explicit authorization following the panefreequoting.com domain decision). Regression clean. Awaiting Inquisitor post-audit."
inquisitor_conditions_resolved:
  C1: "Sentry before_send rate limiter caps at 500 events/hour/worker via token bucket; drained-bucket returns None"
  C2: "Email-only alerts + Sentry mobile app; no SMS/Twilio integration"
mid_sprint_addition:
  T0: "Branding pass — Chris-authorized 2026-05-12 after panefreequoting.com domain decision. Pre-audit predates this. Pure mechanical change, no functional logic. Documented at length in notes/hotfix-4-notes.md."
---

# Hotfix-4 — Observability (DONE)

## Outcome

5 tasks completed (4 from the original draft + T0 added mid-sprint with explicit Chris authorization). The app now has automatic exception capture (Sentry), external uptime monitoring infrastructure (/health endpoint), a complete log catalog, and a written operations runbook with reactive playbooks + proactive maintenance schedule.

| Task | What | Verification |
|---|---|---|
| **T0** | Branding pass: panefreequoting.com domain + Panefree Quotes in email copy. Mid-sprint addition (Chris-authorized) | grep `Window Quoting` returns 0 matches in active code |
| T1 | Sentry SDK + before_send PII scrub + 500/hr token-bucket rate cap (C1) + `/dev/sentry-test` route | 10 unit tests cover scrub + rate limit + version fallback |
| T2 | `/health` endpoint, no auth, no rate limit, DB SELECT 1, version + uptime | 5 unit tests cover happy path + 503 + auth bypass + content-type + uptime monotonicity |
| T3 | Structured logging audit (all pre-existing lines clean) + 3 new INFO logs (REGISTER-SUCCESS, LOGIN-SUCCESS, STRIPE-WEBHOOK) + 17-tag log catalog in DEPLOYMENT.md §9 | grep `app.logger.` shows all lines tag-prefixed |
| T4 | DEPLOYMENT.md §10 Operations runbook (UptimeRobot setup, Sentry alert rules, reactive playbook, maintenance schedule, on-call rotation) + MAINTENANCE_LOG.md | Documentation-only; ops runbook reviewable in the diff |

## Regression evidence (no drift from Hotfix-3)

- `testing/test_mailer.py` — 9/9 PASS
- `testing/test_sentry_hooks.py` (NEW) — 10/10 PASS
- `testing/test_health.py` (NEW) — 5/5 PASS
- `testing/stress_probe.py` — 13/13 probes PASS or expected
- Locust 30u × 45s — **2387 reqs, 0 failures**, p50 16ms / p95 53ms / p99 190ms (well within budget; minor uptick from p50 13 in H3 attributable to Sentry SDK loading + /health route addition, both expected)

## Commits on `hotfix-4`

```
hotfix-4 T0: branding pass — panefreequoting.com + Panefree Quotes
hotfix-4 T1: Sentry SDK + PII scrub + 500/hr rate cap + /dev/sentry-test
hotfix-4 T2: /health endpoint for uptime monitors + readiness probes
hotfix-4 T3: structured logging audit + log catalog
hotfix-4 T4: ops runbook + maintenance schedule + MAINTENANCE_LOG.md
```

Plus the master-side adoption commit (Jade promoting draft → current-sprint).

## What Chris needs at prod-env time

One new env var from H4 (added to `.env.example`):

```
SENTRY_DSN              # from sentry.io project -> Client Keys
```

Plus the H3 set (POSTMARK_SERVER_TOKEN, EMAIL_FROM, EMAIL_FROM_NAME, ADMIN_EMAIL).

UptimeRobot monitor + Sentry alert rules: configure via dashboard post-deploy per DEPLOYMENT.md §10.1 step-by-step.

## Carry-forward from H3 (status)

- **R1** (`.env.example` missing H3 vars) — addressed in H3 post-audit cleanup; verified still in place after T0 edits
- **R2** (`test_account_lifecycle.py` not created) — explicitly deferred to Sprint 5 Ops per backlog
- **R3** (`[EMAIL-VERIFICATION]` URL in log) — accepted as v1-appropriate; H4 T3 catalogue documents this as INFO with "Forensic — verify URL captured as fallback if email failed" disposition

## Open items for Inquisitor post-audit

1. **T0 mid-sprint addition.** Documented authorization but Inquisitor's pre-audit didn't see it. Two questions she may raise:
   a. Is the "remediation of new info" framing acceptable vs. requiring a re-audit cycle?
   b. Should T0-style additions go through a lighter "scope-amendment" process in §13 that's faster than a full re-audit but still leaves a paper trail?
   Both are protocol-shaping questions, not technical defects.

2. **Sentry rate limit is per-worker, not per-DSN-across-workers.** Multi-worker prod will see slightly higher effective cap than 500/hr. Defensible because the goal is "dashboard stays usable under error storm," not exact quota math. Inquisitor may flag this as a future-sprint concern; my read is "fine for v1, revisit at scale."

3. **`/health` doesn't ping Postmark / Stripe / Sentry.** Intentional — those are external dependencies whose failures aren't application failures. But it means /health = 200 while Postmark is down → silently bouncing verification emails. Mitigation: T4's Sentry alert rule on `[EMAIL-SEND-FAILED]` catches this from the application side.

## Phase status

- Stabilize phase: still active. H5 (backups) is next.
- Backlog: clean. No new P0/P1 items surfaced during execution.
