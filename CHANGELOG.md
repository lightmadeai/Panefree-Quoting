# Changelog

All notable changes since the project entered the sprint pipeline. Pre-pipeline
work (Features 1–3, credit-pack ladder, profile DB) is documented in
[`SaaS_BLUEPRINT.md`](SaaS_BLUEPRINT.md), [`SPRINT_1_PORT.md`](SPRINT_1_PORT.md),
and [`AUDIT_LOG.md`](AUDIT_LOG.md). Sprint numbering restarts at 1 with the
pipeline migration (per protocol §5.6).

The format follows [Keep a Changelog](https://keepachangelog.com/) loosely —
sprint manifests in `PLANNING/done/` are the authoritative record.

## Sprint 2 — 2026-05-03 — Pricing update, cancel UX, soft-cap CTA

### Changed
- **Credit pack pricing** updated to Chris's revised tier table:
  - Starter: $9.99 / 8 → **$8.99 / 10** ($0.90/credit)
  - Pro: $49 / 50 → **$39 / 50** ($0.78/credit, 13% off Starter)
  - Studio: $79 / 100 → **$69 / 100** ($0.69/credit, 23% off Starter)
- **Annual Unlimited** price: $149/yr → **$179/yr** (1,000 soft cap unchanged in shape, threshold raised)
- **`SOFT_CAP_THRESHOLD`** default: 500 → **1000**, comparison tightened from `>` to `>=` (notice fires *at* threshold, not strictly above)
- **Soft-cap notice** is now a structured CTA payload (`{count, threshold, message, contact_email, contact_url}`) instead of a bare boolean. Includes a `mailto:` link to `SUPPORT_EMAIL` for high-volume users to request custom pricing.
- **Pricing page UI** rebuilt as a unified 4-tier grid (1 col mobile, 2×2 tablet, 4 across desktop) replacing the previous (Annual hero + 3-pack grid) split. Each card shows per-credit cost and discount-vs-Starter %. Past-due subscribers see the Annual card highlighted with a "Reactivate" button.
- **Account section** swaps "Current period ends:" for "Renews on:" or "Cancels on:" depending on `cancel_at_period_end`.
- **Nav badge** swaps "Unlimited · renews YYYY-MM-DD" for "Unlimited · cancels YYYY-MM-DD" when cancel-pending; access continues through the paid period.

### Added
- **`cancel_at_period_end` column** on `users` (BOOLEAN, default False). Mirrors Stripe's flag from `customer.subscription.updated` events; resets to False when `customer.subscription.deleted` fires.
- **`SUPPORT_EMAIL`** config var (default `support@windowquoting.com`, env-overridable) — surfaced in the soft-cap CTA.
- **`notices.py`** module — pure-Python helper `build_soft_cap_notice()` separated from Flask app for fast unit testing.
- **`test_sprint2.py`** — 16 unit tests covering pricing constants, cancel UX message swap, soft-cap CTA payload shape, and 4-tier grid render across user states (non-subscriber, active, past-due) × Stripe modes (real, simulator).

### Migration notes
- `users.cancel_at_period_end` migration is additive: existing rows backfill to `0`. Idempotent under `_ensure_table_columns` re-runs.
- Stripe Dashboard config from Sprint 1 (Billing Portal: update payment, cancel-at-period-end, view invoices) remains the same — no new dashboard steps for Sprint 2.

## Sprint 1 — 2026-05-03 — Annual unlimited subscription tier

### Added
- **Annual Unlimited subscription** ($149/yr, recurring) alongside existing credit packs. New `/checkout` branch on `pack=="annual"` creates a Stripe `mode=subscription` session; `/webhook/stripe` fans out to handle `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded` (renewal), and `invoice.payment_failed` (past_due transition). All handlers idempotent — UNIQUE(`stripe_tx_id`) blocks duplicate Transaction inserts on Stripe webhook retries.
- **Subscription columns on `users`:** `subscription_status` (TEXT), `subscription_id` (TEXT UNIQUE), `subscription_current_period_end` (DATETIME UTC).
- **Reserve bypass in `/generate`:** active subscribers (whose `subscription_current_period_end > utcnow()`) skip the credit decrement entirely. `past_due` falls through to the credit reserve as a grace mechanism.
- **Heresy #12 fix:** `/generate` reads subscription state off `db.session.get(User, current_user.id)` instead of the cached `current_user` proxy.
- **Soft-cap notice:** subscribers above `SOFT_CAP_THRESHOLD` (initially 500) receive a `soft_cap_notice: true` flag in the `/generate` response. Informational only — generation is never throttled. *(Upgraded to a structured CTA in Sprint 2.)*
- **Stripe Billing Portal route** (`/account/billing-portal`) hands the subscriber off to Stripe's hosted portal for payment-method updates, cancellations, and invoice history.
- **UI:** annual hero card on `/top-up` with "Best Value" badge; nav badge for active subscribers reads "Unlimited · renews YYYY-MM-DD"; account page gains a Subscription section with status, period end, and a "Manage subscription" button.

### Documented
- **Heresies #12–14** in [`AUDIT_LOG.md`](AUDIT_LOG.md):
  - **#12 Lapsed-but-Cached Subscriber** — `/generate` must not read sub state off `current_user` proxy.
  - **#13 Replayed Renewal** — invoice ID is the dedup key on Transaction rows; UNIQUE(`stripe_tx_id`) catches duplicates on webhook retries.
  - **#14 Double-Pay Combo** — UI hides credit packs entirely for active subscribers; existing credit balance shown with "will resume if subscription lapses" annotation.
- **Stripe Dashboard config** as an operational note — Billing Portal must be enabled with: update payment method, cancel-at-period-end (NOT immediate cancel), and view invoices.
