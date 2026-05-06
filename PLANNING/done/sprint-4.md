---
sprint: 4
project: window-quoting
drafted_by: Jade
status: draft
created: 2026-05-03
depends_on: sprint-3-completion
audit_status: approved
---

# Sprint 4 — Ship Readiness: Debug, Stress Test, Production Stripe

## Why
Sprints 1-3 ship all features. Sprint 4 is the gate to production: fix bugs found during manual testing, stress test the payment and quote flows, swap Stripe test keys for live keys, and make the app ready for real customers.

## Tasks

### T1: Bug Fix Sprint — Manual Test Findings
**Acceptance Criteria:**
- Document all bugs found during manual walkthrough of the complete user flow (signup → free credits → buy credits → generate quote → view quote → cancel subscription → resubscribe)
- Fix all P0 (crash/data loss) and P1 (broken flow) bugs
- P2 (cosmetic/minor UX) bugs logged but only fixed if time permits
- Each fix includes a brief note in sprint-4-notes.md explaining the root cause and fix
- Zero P0 bugs remaining at end of sprint

### T2: Stress Test — Quote Generation + Payment Flows
**Acceptance Criteria:**
- Run 100 rapid quote generations from a single free account: verify rate limiting kicks in at 10/hour, verify subscriber bypasses rate limit
- Test all 4 payment flows: Starter ($8.99), Pro ($39), Studio ($69), Annual ($179) — each completes, credits/subscriptions update correctly
- Test edge cases: expired card, webhook delay, double-click checkout, cancelled mid-subscription, credits at 0, credits at soft-cap threshold
- Test cancel-at-period-end flow: subscribe → cancel in portal → verify "Cancels on {date}" message → verify access continues through period end
- Test email verification: new account cannot generate quotes until verified
- Document all test results in `testing/stress-test-results.md`

### T3: Production Stripe Integration
**Acceptance Criteria:**
- Replace all Stripe test keys with live keys (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`)
- Switch Stripe webhook endpoint from test to live mode in Stripe Dashboard
- Set `DEV_MODE=""` (or remove) in production environment — no credit simulator accessible
- Verify `APP_BASE_URL` points to production domain (not localhost)
- Test a real $8.99 Starter purchase with a live card — confirm credit balance updates and Transaction records correctly
- Immediately refund the test purchase via Stripe Dashboard
- Document all production env vars in `CLAUDE.md` with notes on which must be set for live mode

### T4: Production Deployment Checklist
**Acceptance Criteria:**
- `SECRET_KEY` set to a cryptographically random value (not the dev default)
- `DEV_MODE` disabled in production
- Flask `DEBUG=False` in production
- Database file (`sovereign.db`) backed up before migration
- HTTPS enforced on production domain
- Stripe webhook URL configured and verified (responds 200 to test events)
- Environment variable audit: all required vars documented, no test defaults in prod
- Create `DEPLOYMENT.md` with step-by-step production deployment guide
- Create `.env.example` with all required variables (no real secrets)

### T5: Final Polish + Contact Email + Release Notes
**Acceptance Criteria:**
- Remove all `console.log` / `print` debug statements from production code
- Verify all templates render correctly on mobile and desktop
- Verify soft-cap CTA email link works and routes to `/contact`
- Verify `/contact` form persists submissions to DB
- **Contact email (`support@<domain>`) added to:**
  - Site-wide footer on all pages
  - Account/settings page ("Need help? Contact us" link)
  - Error pages (404, 500) as fallback
  - Soft-cap CTA (consistent with footer email)
- Contact email configured as env var `SUPPORT_EMAIL` so it can be changed without redeploy
- Write `RELEASE_NOTES.md` covering v1.0 features across Sprints 1-4
- Update `CHANGELOG.md` through Sprint 4
- Confirm `PROJECT.md` and `CLAUDE.md` are current and accurate

---

## Out of Scope
- Load testing with external tools (k6, Locust) — can be added post-launch
- SEO / marketing landing page
- App Store submission (this is a web app, not mobile)
- Monitoring/alerting setup (post-launch)
- Database migration scripts for existing users (handled in Sprint 2/3)