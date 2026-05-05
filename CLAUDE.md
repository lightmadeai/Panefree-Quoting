# Window Cleaning Engine — Plan Beta

This project follows the **Sprint Pipeline Protocol** — see [`PLANNING/README.md`](PLANNING/README.md). All sprint work flows through `PLANNING/` (drafts → audit → current-sprint → done).

## Project context
- **Stack:** Python / Flask web application
- **Codename (per `shared/projects.md`):** `window-quoting`
- **Marketing name:** "Window Cleaning Sovereign Engine" — but Chris dislikes the "Sovereign" branding on user-facing copy. Keep customer-facing language neutral and professional.
- **Owner:** Jade
- **Phase:** Plan Beta — annual subscription tier shipped (Sprint 1), revised pricing + cancel UX shipped (Sprint 2), abuse prevention + free-tier expansion + account security shipped (Sprint 3). Next: debug pass, then stress test, then launch.

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

## Data model — added columns on `users`

Cumulative across the sprint pipeline. All NULL-able except where noted. Migrations live in `app.py`'s `_ensure_table_columns("users", [...])` block.

| Column | Type | Sprint | Purpose |
|--------|------|--------|---------|
| `subscription_status` | TEXT | 1 | `"active"` / `"past_due"` / `"canceled"` / NULL |
| `subscription_id` | TEXT UNIQUE | 1 | Stripe subscription ID; UNIQUE blocks the double-subscribe race (Heresy #14 guard) |
| `subscription_current_period_end` | DATETIME (UTC) | 1 | Sole field consulted by `/generate` reserve bypass; persists past `canceled` |
| `cancel_at_period_end` | BOOLEAN, default 0 | 2 | Pending-cancellation flag; drives "Cancels on" UI |
| `failed_login_attempts` | INTEGER, default 0 | 3 | Counter for login lockout; reset on success or after lockout fires |
| `locked_until` | DATETIME (UTC) | 3 | Wall-clock end of a login lockout; NULL = not locked |
| `email_verified` | BOOLEAN, default 0 | 3 | Required True before `/generate` succeeds (subscribers included) |
| `email_verification_token` | TEXT, indexed | 3 | uuid hex; cleared on successful verify or after expiry |
| `email_verification_token_expires` | DATETIME (UTC) | 3 | 24h after registration; expired tokens reject the verify link |

UNIQUE on `subscription_id` and the index on `email_verification_token` are created via separate `CREATE [UNIQUE] INDEX IF NOT EXISTS` statements because SQLite's `ALTER TABLE ADD COLUMN` cannot apply UNIQUE/INDEX inline.

A separate `contact_submissions` table holds custom-plan inquiries from the soft-cap CTA — see [`models.py`](models.py) `ContactSubmission`. Created via `db.create_all()` (no ALTER migration needed for new tables).

## Abuse prevention (Sprint 3)

### Rate limiting
Free users (and `past_due` subscribers, who fall through to the credit path) are capped at `RATE_LIMIT_QUOTES_PER_HOUR` (default 10, env-configurable) `/generate` calls per rolling 60-minute window. Active subscribers are exempt — they bypass the credit reserve already and the rate limit follows the same gate.

Tracked via `Quote.created_at` count — no separate rate-limit table. The 429 response carries a countdown that keys off the *oldest* quote in the window falling out (when the rolling count drops back below threshold). Pure helper `notices.build_rate_limit_notice()` builds the payload; `app.py /generate` does the DB query.

### Login lockout
5 wrong passwords → 15-minute cooldown. Even the correct password is rejected during cooldown (otherwise lockout has no teeth). Successful login resets both `failed_login_attempts` and `locked_until`. Unknown emails return the generic "Invalid email or password" without revealing whether the email exists.

### Email verification
Required before any `/generate` call — including subscribers. A registered user gets a 32-char uuid hex token (24h expiry); the verify URL is currently logged to console (no email backend yet — `app.logger.info("[EMAIL-VERIFICATION] ...")`). Pre-Sprint-3 users are grandfathered via `_backfill_email_verified()` (identifies them by absence of token).

### Session timeout
24 hours of idle → cookie expires, user goes back through `/login`. Configured via `app.config["PERMANENT_SESSION_LIFETIME"]`; sessions marked `permanent = True` in `/register` and `/login`.

## Free tier (Sprint 3)
- `STARTING_CREDITS = 10` (was 5). New users get 10 free credits at registration.
- `_ensure_starting_credit_floor()` runs at boot and one-time-bumps any existing user under 10 up to 10. Idempotent — re-runs are no-ops once everyone is at-or-above. The floor migration is intentionally a "soft" guarantee, not a hard one — admin tooling that legitimately sets a balance below the floor would re-bump on next boot. Acceptable for the current scale; needs a `received_topup` flag if it ever isn't.
- Free credits never expire.

## Custom-plan intake (Sprint 3)
The soft-cap CTA links to `/contact` (was `mailto:`) — captures more structured info (company, current volume, expected growth, reply-to email) than an email body. Submissions persist to `ContactSubmission`; admin notification is a structured `app.logger.info()` line. Real email delivery is a future sprint.

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
