---
sprint: 4
project: window-quoting
audit_type: pre-audit
audited_by: Inquisitor
audit_status: approved
created: 2026-05-03
---

# Sprint 4 Pre-Audit — Ship Readiness: Debug, Stress Test, Production Stripe

**Verdict: APPROVED** ✅

Sprint 4 is a production-readiness sprint — no new features, just fixing, testing, and deploying what Sprints 1-3 built. Well-scoped, correctly sequenced, and properly dependent on Sprint 3 completion. 4 non-blocking remarks.

## Task Review

### T1: Bug Fix Sprint — Manual Test Findings ✅
- Clear triage: P0 (crash/data loss) and P1 (broken flow) must be fixed; P2 (cosmetic) is optional
- Falsifiable: "Zero P0 bugs remaining at end of sprint"
- Each fix requires a root cause note in sprint-4-notes.md — good practice
- **Potential scope concern:** This is an open-ended task. The number and severity of bugs found during manual testing is unknown. However, the task is bounded by severity (P0/P1 only mandatory) and the manual test flow is well-defined in T2. Acceptable.

### T2: Stress Test — Quote Generation + Payment Flows ✅
- 6 specific test scenarios, all falsifiable:
  1. 100 rapid quotes → rate limit at 10/hour, subscriber bypass
  2. 4 payment flows → each completes, credits/subscriptions update
  3. Edge cases: expired card, webhook delay, double-click, cancelled mid-sub, credits at 0, soft-cap threshold
  4. Cancel-at-period-end flow → "Cancels on {date}" → access continues through period end
  5. Email verification → new account blocked from quotes until verified
  6. Results documented in `testing/stress-test-results.md`
- Good coverage. The edge cases list is comprehensive.
- **One gap:** No test for the free tier expansion (STARTING_CREDITS=10). Should verify new users get 10 credits and existing users with <10 get the top-up. Minor — can be added during execution.

### T3: Production Stripe Integration ✅
- Clear steps: swap test keys → live keys, configure webhook, disable DEV_MODE, verify APP_BASE_URL
- "Test a real $8.99 Starter purchase with a live card" — this is a real monetary transaction. The "Immediately refund the test purchase via Stripe Dashboard" step handles this correctly.
- Document production env vars in CLAUDE.md
- **🟡 Security note:** Live Stripe keys should NEVER be committed to code or `.env.example`. The task says "no real secrets" in `.env.example` — correct. But Claude should also ensure no test keys remain in any committed file.

### T4: Production Deployment Checklist ✅
- Comprehensive checklist: SECRET_KEY, DEV_MODE, DEBUG=False, DB backup, HTTPS, webhook URL, env audit
- `DEPLOYMENT.md` with step-by-step guide — good operational practice
- `.env.example` with all required variables (no real secrets) — correct
- **🟢 Note:** `app.run(debug=True)` is currently hardcoded in `app.py`. T4 should change this to `debug=os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')` or similar. This is likely something Claude will catch, but worth noting.

### T5: Final Polish + Contact Email + Release Notes ✅
- Remove debug statements (console.log/print) — good cleanup
- Verify templates on mobile and desktop — visual regression check
- Contact email in footer, account page, error pages, soft-cap CTA — comprehensive coverage
- `SUPPORT_EMAIL` already exists as env var (added in Sprint 2) — consistent
- `RELEASE_NOTES.md` covering v1.0 features across Sprints 1-4 — good
- Update `CHANGELOG.md` and `CLAUDE.md`

## Protocol Compliance

| Criterion | Status |
|-----------|--------|
| ≤ 5 tasks | ✅ (5 tasks) |
| All acceptance criteria falsifiable | ✅ (T1 is open-ended but bounded by severity) |
| No scope creep beyond "Why" | ✅ — production readiness is the stated "Why" |
| Dependencies noted | ✅ (`depends_on: sprint-3-completion`) |
| No rebuilding existing features | ✅ — all tasks are additive (fix, test, configure) |
| Out of scope explicit | ✅ (5 items) |

## Non-Blocking Remarks

### 🟡 R1: T1 scope is open-ended
Bug fix sprints are inherently unpredictable. The manual test flow in T2 defines WHAT gets tested, but T1 doesn't constrain HOW MANY bugs might be found. This is acceptable — P0/P1 triage is the right filter — but if manual testing reveals 20+ P0 bugs, Sprint 4 scope will expand significantly. **Recommendation:** If T2 reveals more than 5 P0 bugs, flag it immediately. A high bug count may indicate that Sprints 1-3 need a dedicated debug sprint before T3-T5 can proceed.

### 🟢 R2: Missing test for free tier expansion
T2 doesn't explicitly test the Sprint 3 T2 change (STARTING_CREDITS 5→10). Should add: "New user registration grants 10 credits; existing user with <10 credits receives top-up migration." This is a minor gap — the test list is already comprehensive.

### 🟢 R3: `app.run(debug=True)` must be changed
The development server has `debug=True` hardcoded. Production deployment must set `DEBUG=False`. T4's checklist includes "Flask `DEBUG=False` in production" but doesn't specify how. **Recommendation:** Change `app.run(debug=True)` to `app.run(debug=config.DEBUG, port=config.PORT)` where `DEBUG` defaults to `False` and is only enabled via environment variable.

### 🟢 R4: No rollback plan
T3 involves switching to live Stripe keys. If something goes wrong with the live integration, the task doesn't specify a rollback procedure. **Recommendation:** Add a brief rollback step to T3: "If live integration fails, revert STRIPE_SECRET_KEY to test key, verify test mode still works, and document the failure in sprint-4-notes.md."

## Dependency Note

Sprint 4 depends on Sprint 3 completion. This is correct — Sprint 4's stress test (T2) must test Sprint 3 features (rate limiting, email verification, free tier). If Sprint 3 isn't complete, T2 cannot be executed fully.

## Summary

Clean production-readiness sprint. No new features, no scope creep, no rebuilding existing code. The open-ended bug fix task (T1) is bounded by severity triage. The stress test (T2) is comprehensive with one minor gap (free tier expansion). Production Stripe integration (T3) is well-handled with the refund step.

**Verdict: APPROVED** — Ready for promotion after Sprint 3 completes.