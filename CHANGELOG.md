# Changelog

All notable changes since the project entered the sprint pipeline. Pre-pipeline
work (Features 1–3, credit-pack ladder, profile DB) is documented in
[`SaaS_BLUEPRINT.md`](SaaS_BLUEPRINT.md), [`SPRINT_1_PORT.md`](SPRINT_1_PORT.md),
and [`AUDIT_LOG.md`](AUDIT_LOG.md). Sprint numbering restarts at 1 with the
pipeline migration (per protocol §5.6).

The format follows [Keep a Changelog](https://keepachangelog.com/) loosely —
sprint manifests in `PLANNING/done/` are the authoritative record.

## Sprint 3 — 2026-05-03 — Rate limit, free tier, contact intake, account security

### Added
- **Rate limiting** on `/generate`: 10 quotes per rolling 60-min window for free users (and `past_due` subscribers). Active subscribers exempt. Threshold tunable via `RATE_LIMIT_QUOTES_PER_HOUR` env (default 10). 429 response includes a countdown keyed off the oldest quote in the window. Pure helper `notices.build_rate_limit_notice()`.
- **Email verification gate** on `/generate`: every user (including active subscribers) must verify their email before generating. New columns on `users`: `email_verified` (BOOLEAN), `email_verification_token` (TEXT, indexed), `email_verification_token_expires` (DATETIME). Token is a 32-char uuid hex; expires 24h after registration. **No email backend yet** — verify URL is logged to console (`app.logger.info("[EMAIL-VERIFICATION] …")`). Pre-Sprint-3 users grandfathered via `_backfill_email_verified()` (identifies them by absence of token).
- **`/verify/<token>` route** flips `email_verified=True` and clears the token. Re-clicks fail (one-time link); expired tokens reject with a "request a new one" prompt.
- **Login lockout**: 5 failed attempts → 15-minute cooldown. New columns `failed_login_attempts` (INTEGER, default 0), `locked_until` (DATETIME, nullable). Cooldown rejects even correct passwords (otherwise lockout has no teeth). Successful login resets both fields.
- **Password strength rules** on `/register`: ≥8 chars + ≥1 digit. Pure helper `_password_strength_error()` returns the flash message or None.
- **`/contact` route + `ContactSubmission` model** for custom-plan intake (replaces the soft-cap CTA's old `mailto:` target). Form: company name, current quote volume, expected growth, reply-to email. Persists to DB; admin notification is a structured `app.logger.info()` line. No email backend yet.
- **`build_soft_cap_notice()` signature change**: takes `contact_url` instead of `contact_email`; drops the `contact_email` field from the payload. Caller (e.g., `/generate`) passes `url_for("contact")`. The helper is now URL-agnostic — mailto:, https://, /path all work.
- **Session timeout**: 24h of idle → cookie expires. `app.config["PERMANENT_SESSION_LIFETIME"]` set in app init; sessions marked `permanent = True` in `/register` and `/login`.

### Changed
- **`STARTING_CREDITS = 10`** (was 5). New registrations grant 10 free credits.
- **`_ensure_starting_credit_floor()`** runs at boot and one-time-bumps any existing user under 10 up to the floor. Idempotent — no-op once everyone's at-or-above.
- **NO_CREDITS prompt** on `/generate` now reads "You've used all your free credits. Buy more (from $8.99) or subscribe to Annual Unlimited for unlimited quotes." (was "You've run out of credits."). Frontend still redirects to `/top-up`.
- **Test helpers** (`_register_and_login` in both `test_sprint3.py` and `test_sprint3_pipeline.py`): default password upgraded to `"pw1234567"` (passes T4 strength rules); helpers auto-verify the registered user's email so existing tests don't have to navigate the gate.

### Migration notes
- Six new columns on `users` (one BOOLEAN, two INTEGER-with-default, three TEXT/DATETIME). All additive — backfill defaults handle existing rows.
- One new table: `contact_submissions`. Created via `db.create_all()`; no ALTER migration needed.
- Sprint 1's `subscription_id` UNIQUE INDEX pattern reused for `email_verification_token` (regular index, not UNIQUE — token uniqueness is enforced by uuid generation, not the schema).
- Existing users with `email_verified=False` are grandfathered to True at boot via `_backfill_email_verified()`. The backfill keys off `email_verification_token IS NULL` so post-Sprint-3 unverified users are not wrongly auto-verified.

### Test counts
- 32 tests in `test_sprint3_pipeline.py` (5 rate-limit helper + 3 rate-limit integration + 5 free tier + 6 contact intake + 1 soft-cap CTA wiring + 3 password helper + 2 registration password rules + 2 lockout + 5 email verification + 1 backfill).
- Sprint-2 soft-cap tests in `test_sprint2.py` updated for the new helper signature.
- Legacy `test_sprint3.py` (pre-pipeline Sprint 3): 7 tests still pass after helper update.

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
