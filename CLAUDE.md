# Window Cleaning Engine — Plan Beta

This project follows the **Sprint Pipeline Protocol** — see [`PLANNING/README.md`](PLANNING/README.md). All sprint work flows through `PLANNING/` (drafts → audit → current-sprint → done).

## Project context
- **Stack:** Python / Flask web application
- **Codename (per `shared/projects.md`):** `window-quoting`
- **Marketing name:** "Window Cleaning Sovereign Engine" — but Chris dislikes the "Sovereign" branding on user-facing copy. Keep customer-facing language neutral and professional.
- **Owner:** Jade
- **Phase:** Plan Beta — annual subscription tier shipped (Sprint 1), revised pricing + cancel UX shipped (Sprint 2). Next: debug pass, then stress test, then launch.

## Pricing architecture (post-Sprint 2)

Pricing is centralised in [`config.py`](config.py) — `CREDIT_PACKS` (one-off Stripe `mode=payment`) and `ANNUAL_SUBSCRIPTION` (recurring Stripe `mode=subscription`). Templates derive everything (per-credit cost, discount %) from those constants — no hardcoded prices in the Jinja layer except the Annual sticker price (one location, [`top_up.html`](templates/top_up.html)).

| Tier | Price | Credits | $/credit | Discount vs Starter |
|------|-------|---------|----------|---------------------|
| Starter | $8.99 | 10 | $0.90 | — |
| Pro | $39 | 50 | $0.78 | 13% |
| Studio | $69 | 100 | $0.69 | 23% |
| Annual Unlimited | $179/yr | 1,000 soft cap | ~$0.18 | 97%+ (informally) |

The soft cap is **informational only** — generation is never throttled. When a subscriber reaches it, [`/generate`](app.py) returns a `soft_cap_notice` payload with a CTA pointing to `support@windowquoting.com` for custom-plan conversations.

## Subscription lifecycle

Stripe webhooks drive all subscription state. The `/webhook/stripe` handler fans out to:
- `checkout.session.completed` (mode=subscription) → store sub_id + period_end, mark `active`
- `customer.subscription.updated` → status transitions; mirror `cancel_at_period_end` flag from Stripe
- `customer.subscription.deleted` → mark `canceled`, reset `cancel_at_period_end` to False
- `invoice.payment_succeeded` → renewal; extend period_end; insert dedup'd Transaction
- `invoice.payment_failed` → mark `past_due` (UI falls through to credit reserve as a grace mechanism)

**Cancel-at-period-end:** Stripe sends `cancel_at_period_end=true` on the `customer.subscription.updated` event when a user schedules cancellation via the Billing Portal. We mirror this flag onto the `users` row. The user retains active access until period_end; the UI swaps "Renews on" for "Cancels on" so the state is visible. When the period elapses, `subscription.deleted` fires, `subscription_status` flips to `canceled`, and `cancel_at_period_end` resets so a future re-subscribe starts in the renewing state.

## Data model — subscription columns on `users`

Added across Sprint 1 and Sprint 2. All nullable except `cancel_at_period_end` which has a default of False.

| Column | Type | Purpose |
|--------|------|---------|
| `subscription_status` | TEXT | `"active"` / `"past_due"` / `"canceled"` / NULL |
| `subscription_id` | TEXT UNIQUE | Stripe subscription ID; UNIQUE blocks the double-subscribe race (Heresy #14 guard) |
| `subscription_current_period_end` | DATETIME (UTC) | Sole field consulted by `/generate` reserve bypass; persists past `canceled` |
| `cancel_at_period_end` | BOOLEAN | Pending-cancellation flag; drives "Cancels on" UI |

UNIQUE on `subscription_id` is enforced via a separate `CREATE UNIQUE INDEX IF NOT EXISTS` because SQLite's `ALTER TABLE ADD COLUMN` cannot apply UNIQUE in-place.

## Quirks worth knowing before touching code
- **Stripe flows differ structurally between tiers.** Credit bundles are one-shot (`mode=payment`); Annual is recurring (`mode=subscription`). The `/checkout` route branches on `pack=="annual"` — keep the two paths cleanly separated; mixing them caused the original Sprint 2 draft to fail audit.
- **50-quote history per user** is the pricing-intelligence moat. The "Revenue Recovered" metric on the dashboard depends on quote history being preserved across billing transitions.
- **Race conditions in the credit system** were resolved via a Reserve/Generate/Refund pattern (per Inquisitor's Sovereign Audit). If you touch credit balances, respect that pattern — don't introduce new mutation paths. Active subscribers bypass the reserve entirely; `is_subscriber` is the gating condition both for the reserve skip and for the refund-on-failure (subscribers had nothing reserved, so don't refund).
- **Heresy #12 — never read subscription state off `current_user`.** Always go through `db.session.get(User, current_user.id)` before checking `subscription_status` / `subscription_current_period_end` in `/generate`. The cached LocalProxy can lag behind webhook updates.
- **Pre-pipeline planning history** lives in `SaaS_BLUEPRINT.md`, `SPRINT_1_PORT.md`, and `AUDIT_LOG.md`. Reference for context, but **new planning happens in `PLANNING/`**.

## Sprint workflow
Standard Claude Code slash commands work in this project:
- `/sprint-status` — current sprint state for this project
- `/sprint-start` — begin the active sprint after Jade promotes a draft
- `/sprint-finish` — mark complete after all tasks pass
- `/pipeline-status` (run from anywhere) — global state across all pipeline projects
