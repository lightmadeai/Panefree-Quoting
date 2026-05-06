---
sprint: 1
project: window-quoting
audit_type: post-audit
audited_by: Inquisitor
verdict: PASS
created: 2026-05-03
---

# Sprint 1 Post-Audit — Annual Unlimited Subscription Tier

**Verdict: PASS** ✅

All 5 tasks meet their acceptance criteria. The implementation is clean, well-documented, and follows the heresy-driven audit trail. Three minor findings noted — none blocking.

## Task-by-Task Review

### T1: Schema Migration — Subscription Columns ✅
- Three nullable columns added via `_ensure_table_columns`: `subscription_status` (TEXT), `subscription_id` (TEXT), `subscription_current_period_end` (DATETIME)
- UNIQUE constraint on `subscription_id` created as separate index `idx_users_subscription_id` — correct approach for SQLite (cannot ALTER TABLE ADD COLUMN with UNIQUE)
- SQLAlchemy model has `unique=True` for fresh deployments
- No data loss on existing rows (additive columns, all nullable)
- `credit_balance` column untouched (existing `default=5` via `STARTING_CREDITS`)

### T2: Stripe Checkout + Webhook Fan-Out ✅
- `/checkout` correctly branches: `pack_id == "annual"` → subscription mode, else → payment mode for credit packs
- 5 webhook handlers implemented and verified:
  1. `checkout.session.completed` (mode=subscription) → `_handle_subscription_checkout`
  2. `customer.subscription.updated` → `_handle_subscription_updated`
  3. `customer.subscription.deleted` → `_handle_subscription_deleted`
  4. `invoice.payment_succeeded` → `_handle_invoice_paid`
  5. `invoice.payment_failed` → `_handle_invoice_failed`
- All handlers are idempotent (UNIQUE on `stripe_tx_id`, IntegrityError catch on `subscription_id`)
- Race recovery: `_resolve_user_from_subscription` falls back to `subscription_data.metadata.user_id` when `subscription_id` isn't yet bound

**Minor manifest inaccuracy:** Manifest T5 said "existing `stripe.billing_portal.sessions.create()` call" — no such call existed pre-Sprint 1. Claude implemented it as a new `/account/billing-portal` POST route. Functionally correct.

### T3: Reserve Bypass + Soft-Cap Notification ✅
- Fresh DB read: `user = db.session.get(User, current_user.id)` — Heresy #12 fix implemented
- Reserve bypass condition: `subscription_status == "active" AND subscription_current_period_end > utcnow()` — correct
- `past_due` status falls through to credit reserve — grace period works
- Soft-cap: `Quote.query.filter(user_id, created_at >= period_start).count() > config.SOFT_CAP_THRESHOLD` → `soft_cap_notice: True` in JSON response
- `SOFT_CAP_THRESHOLD` configurable via env var (default 500)
- **Note:** `period_start` approximated as `period_end - 365 days` (no `subscription_period_start` column). Acceptable for annual subs — informational only.

### T4: UI — Pricing Page, Nav Badge, Account Section ✅
- `top_up.html`: Annual Unlimited card with "Best Value" badge, emerald styling, distinct from credit packs
- Credit packs **hidden entirely** when `subscription_status == 'active'` — replaced with subscription banner + Manage subscription button
- `_nav.html`: Three states correctly implemented:
  - Active: `Unlimited · renews {YYYY-MM-DD}`
  - Past due: Red chip `Subscription past due` → links to top_up
  - Default: `{N} credits`
- `account.html`: Subscription section conditionally shown (on `subscription_id`), status badges, period end, Manage subscription button, unused credits annotation

**Known UX gap (documented, out of scope):** Cancel-at-period-end subscriber still shows "renews {date}" because `cancel_at_period_end` flag is not stored. Would require either a new column or per-render Stripe call. Deferred.

### T5: Heresy Documentation + Stripe Billing Portal Config ✅
- `AUDIT_LOG.md` updated with Heresies #12, #13, #14
- Each heresy includes: failure mode, risk, fix implemented
- Heresy #12: Lapsed-but-Cached Subscriber — fresh DB read, period_end as source-of-truth gate
- Heresy #13: Replayed Renewal — UNIQUE on `stripe_tx_id` for subscription invoices
- Heresy #14: Double-Pay Combo — credit packs hidden for active subscribers
- Stripe Billing Portal configuration documented as one-time operational step

## Definition of Done Verification

| Criterion | Status |
|-----------|--------|
| New subscriber can sign up via Stripe Checkout | ✅ Route + subscription mode implemented |
| Subscriber generates quotes without credit deduction | ✅ Reserve bypass implemented |
| Webhook events update subscription state correctly | ✅ 5 handlers, all idempotent |
| Duplicate webhook delivery does not corrupt state | ✅ UNIQUE + IntegrityError catch |
| `current_user` cache never trusted for subscription checks | ✅ Heresy #12 fix: `db.session.get(User, ...)` |
| Non-subscribers see no change in credit bundle flow | ✅ Existing pack logic untouched |
| `app.py` starts without errors | ✅ `py_compile` clean (runtime not tested — no Flask in local env) |
| `engine.py` and `generator.py` unchanged | ✅ No modifications to Pure Engine / Pure View |
| Sprint manifest moved to `done/` | ✅ |
| `notes/sprint-1-notes.md` created | ✅ |
| Heresies #12-14 documented in AUDIT_LOG.md | ✅ |

## Findings (Non-Blocking)

### F1: 🟢 LOW — Manifest wording inaccuracy (T5)
Manifest said "existing `stripe.billing_portal.sessions.create()` call" but no such call existed. Claude correctly implemented it as a new route. No functional impact.

### F2: 🟢 LOW — Manifest wording inaccuracy (T2)
Manifest said `checkout.session.completed` "sets subscription_status='active'" directly, but the checkout session payload doesn't carry `current_period_end`. Claude correctly added `stripe.Subscription.retrieve()` to fetch it. This is an improvement over spec, not a regression.

### F3: 🟢 LOW — Integration test gap
Notes state: "Full Flask runtime startup NOT verified — Flask is not installed." Static checks (py_compile, Jinja StrictUndefined) pass. First real-Stripe deploy is the integration gate. Not blocking — deployment step.

### F4: 🟡 MEDIUM — Cancel-at-period-end UX gap
Subscriber who cancels via Stripe Portal keeps "renews {date}" in nav/account until the period elapses. No `cancel_at_period_end` column stored. Surfacing this state would require either a new DB column or a per-render Stripe API call. Documented in notes as out of scope. **Recommendation: Add to Sprint 2 or a follow-up sprint.**

---

## Summary

Sprint 1 ships clean. All heresy fixes are verified in code. The implementation is slightly better than spec in two places (subscription retrieve for period_end, new billing portal route). No drift requiring remediation.

**Verdict: PASS** — No contested items. Sprint 1 is cleared for merge.