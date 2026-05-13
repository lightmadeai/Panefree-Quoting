---
label: hotfix-4
project: window-quoting
auditor: inquisitor
date: 2026-05-12
verdict: PASS
blocking_count: 0
nonblocking_count: 3
---

# Hotfix-4 Post-Audit — Observability: Sentry + Health Check + Ops Runbook

**Auditor:** The Inquisitor
**Date:** 2026-05-12
**Branch:** `hotfix-4` (6 commits: T0 + T1-T4 + close-out)
**Verdict:** ✅ PASS — all 5 tasks verified against acceptance criteria. 0 blocking findings. 3 non-blocking remarks.

---

## Task Verification Matrix

| Task | Description | Verified | Notes |
|------|-------------|:--------:|-------|
| T0 | Branding pass (panefreequoting.com + Panefree Quotes) | ✅ | Mid-sprint addition, Chris-authorized. Zero functional logic touched. `Window Quoting` grep = 0 matches in active code. |
| T1 | Sentry SDK + PII scrub + 500/hr rate cap + /dev/sentry-test | ✅ | `sentry-sdk[flask]~=2.59.0` pinned. Init before Flask app creation. `before_send` scrubs 5 PII fields case-insensitively + token-bucket rate cap. `/dev/sentry-test` gated identically to `/dev/grant-credits`. 10 unit tests pass. |
| T2 | /health endpoint | ✅ | No auth, `@csrf.exempt`, `@limiter.exempt`, `SELECT 1` DB check, 503 on failure, `time.monotonic()` uptime, VERSION file SHA fallback to `"dev"`. 5 unit tests pass. |
| T3 | Structured logging audit + log catalog | ✅ | All `app.logger.warning` and `app.logger.error` lines carry `[TAG]` prefixes. New INFO logs: `[REGISTER-SUCCESS]`, `[LOGIN-SUCCESS]`, `[STRIPE-WEBHOOK]`. 17-tag catalog in DEPLOYMENT.md §9. All tags in catalog match code (including `mailer.py` tags). |
| T4 | Ops runbook + maintenance schedule + MAINTENANCE_LOG.md | ✅ | DEPLOYMENT.md §10 covers UptimeRobot setup, Sentry alert rules (3 rules), reactive playbook for 5 alert types, maintenance schedule table (Weekly/Monthly/Quarterly/Annually/Reactive), solo-ops on-call rotation. `MAINTENANCE_LOG.md` in repo root, empty and ready. |

---

## Inquisitor Conditions Verification

| Condition | Status | Evidence |
|-----------|:------:|---------|
| C1: Sentry free tier + `before_send` rate limiter cap at 500/hr | ✅ PASS | Token-bucket implementation at `_SENTRY_RATE_CAP_PER_HOUR = 500`. Per-worker (documented trade-off). Drops log to stderr with `[SENTRY-RATE-LIMITED]`. |
| C2: Email-only alerts for v1 + Sentry mobile app. No SMS/Twilio. | ✅ PASS | DEPLOYMENT.md §10.1 explicitly states "email-only" and "no SMS / Twilio." Sentry mobile app listed as push channel. |

---

## T0 Mid-Sprint Addition Assessment

T0 (branding pass) was added after pre-audit with Chris's explicit authorization. The notes document the rationale thoroughly: domain decision landed after H3 merge, branding needed before H6 live email test.

**Inquisitor assessment:** Acceptable as "remediation of new info." The change is purely mechanical (39 insertions / 33 deletions across 13 files, all display strings and defaults). Zero functional logic touched. No re-audit cycle needed.

**Protocol suggestion for future:** Consider a lightweight §13 "scope-amendment" path that requires (1) Chris authorization in transcript, (2) executor notes documenting the delta, and (3) Inquisitor post-audit covering the full scope including the amendment. This is what happened de facto; making it de jure removes ambiguity.

---

## Regression Verification

- **Unit tests:** 24/24 pass (10 Sentry hooks + 5 health + 9 mailer)
- **Stress probes:** Clean (13/13 per close-out report)
- **Locust:** 2387 reqs, 0 failures, p50 16ms / p95 53ms / p99 190ms
- **No functional regressions** from T0 branding pass or T1-T4 additions

---

## Non-Blocking Remarks

### R1: Per-Worker Rate Limit vs. Per-DSN
The Sentry rate cap is per-worker (token bucket in process memory). Multi-worker gunicorn will see `500 × workers` effective cap. The notes explicitly acknowledge this trade-off and defend it as "dashboard stays usable under error storm" being the goal, not exact quota math. **Acceptable for v1.** Flag for revisit if the app scales beyond single-digit workers.

### R2: `/health` Does Not Probe External Dependencies
By design, `/health` only checks `SELECT 1` on the local DB. Stripe, Postmark, and Sentry outages won't trigger UptimeRobot alerts. The mitigation is documented: Sentry alert on `[EMAIL-SEND-FAILED]` catches Postmark failures; Stripe Dashboard is canonical for payment issues. **Acceptable for v1.** A future `/health/deep` endpoint could optionally probe externals.

### R3: H3 Carry-Forward Remarks Still Open
- **R1-H3** (`.env.example` missing H3 vars) — H4 added SENTRY_DSN section but H3 vars (POSTMARK_SERVER_TOKEN, EMAIL_FROM, EMAIL_FROM_NAME, ADMIN_EMAIL) are already present in .env.example from H3. ✅ Resolved.
- **R2-H3** (`test_account_lifecycle.py` doesn't exist) — Still deferred to Sprint 5 Ops. ✅ Tracked.
- **R3-H3** (`[EMAIL-VERIFICATION]` log includes full verify URL) — H4 T3 catalog documents this as INFO with "Forensic — verify URL captured as fallback if email failed." ✅ Acceptable for v1.

---

## Summary

| Category | Count |
|----------|-------|
| 🔴 Blocking | 0 |
| 🟡 Non-Blocking | 3 |
| ✅ Tasks Verified | 5/5 |
| ✅ Conditions Met | 2/2 |

**Verdict: ✅ PASS** — Hotfix-4 is approved for merge. All acceptance criteria met, both Inquisitor conditions satisfied, no blocking findings. T0 mid-sprint addition accepted as remediation of new info. Proceed to H5 (backups).