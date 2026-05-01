# 🏗️ SaaS Blueprint: Window Sovereign Credit System
**Model**: Plan Beta (Pay-Per-Quote)
**Status**: Draft Specification

## 🎯 Objective
Transition the Window Cleaning Sovereign Engine from a local tool to a monetized SaaS by implementing a credit-based payment system.

## ⚙️ Logic Flow
1. **User Authentication**: User logs in via a simple account system (email/password).
2. **Credit Balance**: Each user has a `credit_balance` in the database.
3. **The Transaction**:
    - User configures a quote in the UI.
    - User clicks "Generate PDF."
    - **System Check**: `if user.credit_balance >= 1`:
        - Deduct 1 credit from `user.credit_balance`.
        - Trigger `generator.py` to produce the PDF.
        - Deliver PDF.
    - **Else**:
        - Redirect user to "Top-Up" page.
        - Prompt for credit purchase.

## 🗄️ Database Schema (Conceptual)
**Table: `users`**
- `user_id` (PK, UUID)
- `email` (Unique)
- `password_hash`
- `credit_balance` (Integer)
- `created_at` (Timestamp)

**Table: `transactions`**
- `tx_id` (PK, UUID)
- `user_id` (FK)
- `amount_paid` (Decimal)
- `credits_added` (Integer)
- `timestamp` (Timestamp)
- `stripe_tx_id` (String)

## 🔌 API Implementation Plan
- **`GET /api/credits`**: Returns the current balance of the authenticated user.
- **`POST /api/generate-quote`**:
    - Validates session.
    - Checks credit balance.
    - Atomic operation: `UPDATE users SET credit_balance = credit_balance - 1 WHERE user_id = ? AND credit_balance > 0`.
    - If successful, calls `generator.py`.
- **`POST /api/purchase-credits`**:
    - Integrates with Stripe Checkout.
    - Upon successful webhook, updates `users.credit_balance`.

## 🛠️ Integration with `engine.py` & `app.py`
- **`app.py`**: Add a middleware layer to check for authentication before allowing access to the quoting engine.
- **`engine.py`**: Remains a "Pure Engine." It doesn't care about credits; it just calculates. The credit check happens in the `app.py` (the View/Controller layer) *before* the engine's results are passed to the generator.
- **`generator.py`**: Now gated by the credit check.

---
**Sovereign Note**: This ensures that "The Engine" remains pure logic, while the "SaaS Wrapper" handles the money.

---

## 💳 Feature 4 — Annual Unlimited Subscription (planned, next sprint)

### 🎯 Objective
Layer a recurring annual subscription on top of the existing pay-per-quote credit system to capture high-volume users who would otherwise grind through repeated top-up packs. **Push intent**: high-volume users should see annual as the obviously-correct choice.

### 💰 Pricing context (already shipped, commit `8718a57`)
| Tier | Quantity | Price | Per-quote |
|---|---|---|---|
| Starter | 8 credits | $9.99 | $1.249 |
| Pro | 50 credits | $49 | $0.98 |
| Studio | 100 credits | $79 | $0.79 |
| **Annual** | **Unlimited** | **$149/yr** | breaks even at ~189 quotes/year (~3.6/wk) |

Studio was deliberately shrunk from 200 → 100 credits in `8718a57` so high-volume use has only one rational path. Annual at $149 vs Studio at $79 (100 credits) = annual pays for itself at ~189 quotes; anyone doing 4+ quotes/week should subscribe.

### 🗄️ Schema additions
**`users` table** — three new columns, migrated via existing `_ensure_table_columns` helper:
- `subscription_status` (TEXT, nullable) — `"active"`, `"past_due"`, `"canceled"`, or NULL for never-subscribed
- `subscription_id` (TEXT, nullable, UNIQUE) — Stripe subscription ID; UNIQUE blocks the "double-subscribe" race
- `subscription_current_period_end` (DATETIME, nullable) — UTC; the only thing the reserve check actually reads. Webhook updates this on every `invoice.payment_succeeded` (renewal).

Existing `credit_balance` stays. Subscriptions don't delete or freeze credits — a subscriber's credits just sit unused until/unless their subscription lapses.

### 🔌 Stripe surface area changes
**`/checkout` route** — branch on whether the request targets a credit pack or the annual sub:
- Pack: existing `mode="payment"` flow (unchanged).
- Annual: new branch — `mode="subscription"`, `line_items` with `price_data.recurring.interval="year"`, `metadata={"product": "annual"}` so the webhook can route correctly.

**`/webhook/stripe` handler** — currently only handles `checkout.session.completed` for `mode="payment"`. Needs to fan out:
- `checkout.session.completed` (mode=subscription) → set `subscription_status="active"`, store subscription ID + period_end
- `customer.subscription.updated` → handle status transitions, plan changes, cancel-at-period-end
- `customer.subscription.deleted` → set status to `"canceled"`, leave period_end so user keeps access until end of paid period
- `invoice.payment_succeeded` → renewal: extend `subscription_current_period_end` to the new period
- `invoice.payment_failed` → set `subscription_status="past_due"` (still has access during grace period; Stripe handles the retry schedule)

### ⚙️ Reserve-logic change in `/generate`
Currently does `UPDATE users SET credit_balance = credit_balance - 1 WHERE id = :uid AND credit_balance > 0`. Add a subscription-bypass branch *before* the reserve:
```
if user.subscription_status == "active" and user.subscription_current_period_end > utcnow():
    # No credit reserve — unlimited access. Skip reserve, skip refund branch.
    proceed_to_render()
else:
    # Existing Reserve → Generate → Refund-on-failure flow.
    ...
```
Read the user fresh from the DB inside the request — don't trust `current_user` cache (see Heresy #12 below).

### 🚫 New Heresies to document in AUDIT_LOG.md before coding

**Heresy #12: The Lapsed-but-Cached Subscriber**
- **Failure**: A webhook downgrades the user (subscription lapsed), but the `current_user` proxy still reflects the pre-lapse state for the rest of their session. They get free unlimited access until they log out.
- **Risk**: Revenue leak proportional to session duration after lapse.
- **Sovereign Fix**: Reserve check reads the user row fresh via `db.session.get(User, current_user.id)` — never the cached `current_user` proxy. Cheap (one indexed primary-key lookup per generate).

**Heresy #13: The Replayed Renewal**
- **Failure**: Each annual renewal fires a fresh `invoice.payment_succeeded` event with a new invoice ID. The existing `Transaction.stripe_tx_id` UNIQUE constraint (Heresy #3 fix) keys off `checkout.session.id` — it doesn't dedupe renewal events. A retried renewal webhook could extend `period_end` twice, giving the user 2 years of access for one payment.
- **Risk**: Free year of access on every webhook retry storm.
- **Sovereign Fix**: Either (a) UNIQUE on `Transaction.stripe_tx_id` covering renewal invoice IDs (cleanest — same pattern as Heresy #3), or (b) idempotency via Stripe event ID stored separately. Pick (a). Update of `period_end` happens inside the same transaction that inserts the Transaction row; if the insert collides on UNIQUE, rollback leaves period_end unchanged.

**Heresy #14: The Double-Pay Combo**
- **Failure**: User buys a credit pack, then subscribes (or vice versa). Both charges land. UI doesn't clearly communicate that subscription overrides credits, so user feels double-charged.
- **Risk**: Refund requests, churn, support burden. Not technically a bug — both products are real. Pure UX/comms problem.
- **Sovereign Fix**: Top-up page hides credit packs entirely when `subscription_status="active"` (replaced with "Your subscription gives you unlimited quotes through {period_end}"). Account page surfaces an "Unused credits: N (will resume if subscription lapses)" line so users know their pack purchases aren't lost. No refund logic needed — credits just wait.

### 🎨 UI surface
- **`top_up.html`**: New "Annual Unlimited" card visually distinct from packs (different color, "Best Value" or "Most Popular" badge, year-long timeframe callout). Hide packs entirely for active subscribers.
- **`_nav.html`**: Credit badge currently `{{ current_user.credit_balance }} credits`. For active subscribers: `Unlimited · renews YYYY-MM-DD`. For past_due: red `Subscription past due` chip linking to billing.
- **`account.html`**: New "Subscription" section with status, current period end, "Manage subscription" button → Stripe Billing Portal (self-serve cancel/upgrade/payment-method-update). Free to enable, dramatically reduces support load vs custom cancellation flow.

### 📋 Open design questions for tomorrow's session
1. **Cancel-at-period-end vs cancel-immediately**. Recommend cancel-at-period-end (industry standard, no proration math, user keeps paid-through access).
2. **Grace period on `past_due`**. Stripe retries failed payments for ~7 days by default. During that window: keep `subscription_status="active"`-equivalent behavior, or downgrade immediately? Recommend "active during grace" — bypass the reserve until either the retry succeeds (back to `active`) or the subscription transitions to `canceled` after retries exhaust.
3. **Annual upsell prompts**. Once a user buys their second credit pack within 30 days, show a soft prompt on the top-up page: "You've bought N quotes in the last month. Annual unlimited would have cost $X less." Probably sprint 5.
4. **Stripe Billing Portal config**. Needs setup in Stripe Dashboard (one-time, ~10 min). Determines what the portal lets users do: update payment method, cancel, switch plans (if we ever add monthly).

### ✅ Sequencing for tomorrow's sprint
1. Read this section + AUDIT_LOG.md.
2. Confirm pricing ($149/year) and Heresy fixes with user before writing code.
3. Schema migration (3 new columns).
4. Sanitize question of Heresy #13 (UNIQUE on the right column).
5. Webhook fan-out — most error-prone piece, write with idempotency tests.
6. Reserve bypass in `/generate`. Read user fresh.
7. UI: top_up.html, nav, account.html, billing portal link.
8. Commit Heresies #12-14 as a separate AUDIT_LOG.md entry alongside the feature commit.

---
**Sovereign Note (Feature 4 corollary)**: The engine and generator stay untouched. Subscription is purely a controller-layer concern — it gates whether the credit reserve runs, but the Pure View / Pure Engine separation holds. If subscription logic ever leaks into `engine.py` or `generator.py`, that's a regression.
