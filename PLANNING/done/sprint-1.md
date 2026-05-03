---
sprint: 1
project: window-quoting
drafted_by: Jade
research_refs: []  # Solis: pull if needed → research/sprint-1-annual-pricing.md
content_refs: []   # Luna: pull if needed → content/sprint-1-pricing-copy.md
audited_by: Inquisitor
audit_status: approved
status: done
created: 2026-05-02
---

# Sprint 1 — Annual Unlimited Subscription Tier

## Why
Window Cleaning Engine has credit bundles shipped ($9.99/8, $49/50, $79/100 — commit `8718a57`). High-volume users who exceed ~4 quotes/week have no rational path except repeated top-ups. An annual subscription at $149/yr captures this segment, increases LTV, and makes the "unlimited" promise a real selling point. This is the last revenue tier before debug + stress test.

## Goals
- Add an annual "unlimited" subscription tier ($149/yr) alongside existing credit bundles
- Implement Stripe recurring billing with proper webhook handling
- Soft-cap "unlimited" with notification (not silent failure)
- UI reflects subscription state across pricing, nav, and account pages

## Tasks

- [ ] **T1: Schema migration — subscription columns**
  - touches: `models.py` (User model), `app.py` (`_ensure_table_columns`)
  - acceptance: Three new nullable columns on `users` table: `subscription_status` (TEXT — `"active"`, `"past_due"`, `"canceled"`, or NULL), `subscription_id` (TEXT, UNIQUE — Stripe subscription ID, blocks double-subscribe race), `subscription_current_period_end` (DATETIME — UTC, the only field the reserve bypass reads). Migration via existing `_ensure_table_columns` helper. No data loss on existing rows. `credit_balance` column stays untouched — subscribers' credits sit unused until lapse.

- [ ] **T2: Stripe checkout + webhook fan-out for subscriptions**
  - touches: `app.py` (`/checkout` route, `/webhook/stripe` handler)
  - acceptance: `/checkout` branches on request type — credit packs use existing `mode="payment"` flow (unchanged), annual sub uses `mode="subscription"` with `price_data.recurring.interval="year"` and `metadata={"product": "annual"}`. Webhook handler fans out: (1) `checkout.session.completed` (mode=subscription) → sets `subscription_status="active"`, stores subscription ID + period_end; (2) `customer.subscription.updated` → handles status transitions and cancel-at-period-end; (3) `customer.subscription.deleted` → sets `subscription_status="canceled"`, leaves `period_end` so user keeps access through paid period; (4) `invoice.payment_succeeded` → extends `period_end` to new period, inserts Transaction row with UNIQUE `stripe_tx_id` (Heresy #13 fix — renewal invoice IDs are deduped the same way as checkout sessions); (5) `invoice.payment_failed` → sets `subscription_status="past_due"`. All webhook mutations are idempotent — duplicate events must not corrupt state.

- [ ] **T3: Reserve bypass + soft-cap notification**
  - touches: `app.py` (`/generate` route)
  - acceptance: Before the existing `UPDATE users SET credit_balance = credit_balance - 1` reserve, check subscription: if `user.subscription_status == "active"` AND `user.subscription_current_period_end > utcnow()`, skip the credit reserve entirely and proceed to render. **Read user fresh from DB** via `db.session.get(User, current_user.id)` — never the cached `current_user` proxy (Heresy #12 fix). If subscription is `"past_due"`, fall through to credit reserve (grace period = use credits until subscription resolves). **Soft-cap notification**: when a subscriber's quote count in the current subscription period exceeds 500, include a `soft_cap_notice: true` field in the JSON response. The notice is informational only — it does NOT block or throttle generation. The 500 threshold is configurable via a `SOFT_CAP_THRESHOLD` env var (default: 500).

- [ ] **T4: UI — pricing page, nav badge, account section**
  - touches: `templates/top_up.html`, `templates/_nav.html`, `templates/account.html`
  - acceptance: (1) `top_up.html` adds an "Annual Unlimited — $149/yr" card visually distinct from credit packs (different accent color, "Best Value" badge). Credit packs are **hidden entirely** when `subscription_status="active"` — replaced with "Your subscription gives you unlimited quotes through {period_end}" and a "Manage subscription" link. (2) `_nav.html` credit badge: for active subscribers shows `Unlimited · renews {YYYY-MM-DD}`; for `past_due` shows red `Subscription past due` chip linking to top-up. (3) `account.html` adds a "Subscription" section: status, current period end, "Manage subscription" button linking to Stripe Billing Portal. Shows "Unused credits: N (will resume if subscription lapses)" for subscribers who also have credits. All three templates render correctly with no Jinja errors for both subscribed and non-subscribed users.

- [ ] **T5: Heresy documentation + Stripe Billing Portal config**
  - touches: `AUDIT_LOG.md`, Stripe Dashboard (one-time config)
  - acceptance: `AUDIT_LOG.md` updated with Heresies #12 (Lapsed-but-Cached Subscriber), #13 (Replayed Renewal — UNIQUE fix documented), #14 (Double-Pay Combo — UX fix documented). Each heresy has: failure mode, risk, fix implemented. Stripe Billing Portal enabled in Stripe Dashboard with: update payment method, cancel subscription (cancel-at-period-end), view invoices. Portal URL wired into `account.html` "Manage subscription" button via existing `stripe.billing_portal.sessions.create()` call.

## Out of scope
- Debug pass (subsequent sprint)
- Stress test (subsequent sprint)
- Monthly subscription tier
- Cancel-immediately mode (cancel-at-period-end only)
- Proration logic
- Annual upsell prompts ("you've bought N quotes this month")
- Quote count dashboard / analytics for subscribers
- Changes to `engine.py` or `generator.py` (Pure Engine / Pure View invariant holds)

## Open questions
- **Debug/stress-test phasing**: Should Sprint 2 be "debug + fix" and Sprint 3 be "stress test", or combine into one sprint? Recommend separate — debug catches code issues, stress test validates infra under load. Different failure modes, different tooling.
- **Soft-cap threshold**: 500 quotes/year as the notification trigger? This is ~1.4x the break-even point (189 quotes to beat Studio at $79/100). A user hitting 500 is clearly power-user territory but nowhere near abuse. Configurable via env var, so easy to adjust post-launch.
- **Grace period behavior**: During Stripe's ~7-day retry window for failed payments, subscriber retains "active" equivalent access? Or immediate downgrade to credit reserve? Recommend "active during grace" (per SaaS Blueprint §Feature 4).

## Definition of done
- All tasks checked
- New subscriber can sign up for annual plan via Stripe Checkout
- Subscriber can generate quotes without credit deduction (reserve bypass works)
- Webhook events (success, renewal, failure, cancel) all update subscription state correctly
- Duplicate webhook delivery does not corrupt state (idempotent)
- `current_user` cache is never trusted for subscription checks (Heresy #12)
- Non-subscribers see no change in existing credit bundle flow
- `app.py` starts without errors; `engine.py` and `generator.py` are unchanged
- Commit on `sprint-1` branch
- `notes/sprint-1-notes.md` created
- Heresies #12-14 documented in AUDIT_LOG.md

## Project-specific note
This is Sprint 1 under the new sprint pipeline (migrated from pre-pipeline SPRINT_1_PORT.md structure). Sprint numbering restarts at 1 per §5.6 convention. Legacy planning files (SPRINT_1_PORT.md, SaaS_BLUEPRINT.md, AUDIT_LOG.md) are preserved as historical reference; new planning lives in PLANNING/.