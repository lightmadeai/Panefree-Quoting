---
sprint: 5
project: window-quoting
drafted_by: Jade
status: draft
created: 2026-05-05
depends_on: sprint-4-completion
audit_status: pending
---

# Sprint 5 — Production Deployment Cutover

## Why
Sprint 4 handles all code-side ship readiness. Sprint 5 is the operational deployment sprint — everything that requires live infrastructure, real Stripe keys, HTTPS configuration, and human verification. This is the final gate to production.

## Tasks

### T1: Merge Sprint 4 + Final Code Review
**Acceptance Criteria:**
- Sprint 4 branch merged to master with no conflicts
- Quick smoke test on merged master: app boots, pages load, no import errors
- Chris reviews the diff from Sprint 3 master to Sprint 4 merge for any surprises

### T2: Production Stripe Integration
**Acceptance Criteria:**
- Replace all Stripe test keys with live keys in production environment vars (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`)
- Switch Stripe webhook endpoint from test to live mode in Stripe Dashboard
- Set `DEV_MODE=""` (or remove) in production environment — no credit simulator accessible
- Verify `APP_BASE_URL` points to production domain (not localhost)
- Test a real $8.99 Starter purchase with a live card — confirm credit balance updates and Transaction records correctly
- Immediately refund the test purchase via Stripe Dashboard
- Confirm webhook receives and processes live events

### T3: Production Security Hardening
**Acceptance Criteria:**
- `SECRET_KEY` set to a cryptographically random value in production (not the dev default)
- `DEV_MODE` disabled in production
- Flask `DEBUG=False` in production
- HTTPS enforced on production domain
- Database file (`sovereign.db`) backed up before going live
- All test/debug routes removed or disabled
- Environment variable audit: no test defaults in prod, all required vars set

### T4: Manual Walkthrough + Visual QA
**Acceptance Criteria:**
- Complete user flow walkthrough on production: signup → free credits → buy credits → generate quote → view quote → cancel subscription → resubscribe
- All templates render correctly on mobile (2+ devices/browsers) and desktop
- Error pages (404, 500) display correctly with contact email
- Footer appears on all pages with contact email
- Account/settings page shows contact link
- Soft-cap CTA email link works end-to-end

### T5: Go Live Verification
**Acceptance Criteria:**
- Production app accessible at production URL
- HTTPS certificate valid and not expiring within 30 days
- Stripe live mode processing real payments
- Webhook receiving and processing live events
- Contact form submissions reaching the database
- All Sprint 4 documentation (`DEPLOYMENT.md`, `.env.example`, `RELEASE_NOTES.md`, `CHANGELOG.md`) is accurate and matches production state
- Chris signs off: "Ship it."

---

## Out of Scope
- Load testing with external tools (k6, Locust) — can be added post-launch
- SEO / marketing landing page
- App Store submission (this is a web app, not mobile)
- Monitoring/alerting setup (post-launch)
- Database migration scripts for existing users (handled in Sprint 2/3)

## Notes
- This sprint requires Chris's direct involvement for live Stripe testing, manual QA, and final sign-off.
- Inquisitor verifies code-side items; Chris verifies all live-environment items.
- Sprint 5 cannot be partially completed — either we go live or we don't.