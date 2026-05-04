---
sprint: 2
project: window-quoting
drafted_by: Jade
redraft: true
redraft_reason: Original draft proposed rebuilding features that already exist (credit packs, checkout, credit_balance column). Inquisitor rejected with 5 blockers. Redraft aligns with shipped Sprint 0/1 code.
research_refs: [research/sprint-2-pricing.md]
audited_by: Inquisitor (pending re-audit)
audit_status: approved
status: done
created: 2026-05-03
redrafted: 2026-05-03
depends_on: sprint-1-post-audit (PASS)
---

# Sprint 2 — Pricing Update + Cancel UX + Soft-Cap CTA

## Why
Sprint 1 shipped the annual subscription tier on top of existing credit packs. Sprint 2 updates pricing to Chris's revised tier table, fixes the cancel-at-period-end UX gap (Sprint 1 post-audit finding F4), and adds the soft-cap CTA that converts high-volume users into custom-plan leads.

## What Already Exists (do NOT rebuild)
- `CREDIT_PACKS` in `config.py` — inline pricing, no pre-created Stripe Prices
- `ANNUAL_SUBSCRIPTION` in `config.py` — $149/yr, interval=year
- `credit_balance` column on User model (default=5, from Sprint 0)
- `/checkout` route handles both packs (mode=payment) and annual (mode=subscription)
- `SOFT_CAP_THRESHOLD` env var (default=500) — informational notice only
- Subscriber bypass: `/generate` skips credit deduction for `subscription_status=active`

## Revised Pricing (Chris + Solis, 2026-05-03)

| Tier | Price | Credits | $/Credit | Discount |
|------|-------|---------|----------|----------|
| Starter | $8.99 | 10 | $0.90 | — |
| Pro | $39 | 50 | $0.78 | 13% |
| Studio | $69 | 100 | $0.69 | 23% |
| Unlimited | $179/yr | 1,000 softcap | ~$0.015/mo | 97%+ |

Deltas vs. current `config.py`:
- Starter: $9.99/8 → $8.99/10
- Pro: $49/50 → $39/50
- Studio: $79/100 → $69/100
- Annual: $149 → $179
- Soft cap: 500 → 1,000

## Tasks

### T1: Pricing Update in Config + Templates
**Acceptance Criteria:**
- `CREDIT_PACKS` in `config.py` updated to: Starter $8.99/10, Pro $39/50, Studio $69/100
- `ANNUAL_SUBSCRIPTION` price updated to $179/yr (17900 cents)
- `SOFT_CAP_THRESHOLD` default changed from 500 to 1000
- All templates that display pricing (`index.html`, `top_up.html`, `account.html`) updated to match new values
- `/checkout` creates correct Stripe sessions with new prices
- Unit test: `CREDIT_PACKS["starter"]["price_cents"] == 899` and `ANNUAL_SUBSCRIPTION["price_cents"] == 17900`

### T2: Cancel-at-Period-End UX
**Acceptance Criteria:**
- New column `cancel_at_period_end` (Boolean, default False) on User model
- On `customer.subscription.updated` webhook, if `cancel_at_period_end=True`, set user's `cancel_at_period_end=True`
- Account section shows "Cancels on {date}" instead of "Renews on {date}" when `cancel_at_period_end=True`
- Nav badge still shows "Unlimited" during the active period (subscriber keeps access through period end)
- When subscription fully cancels (period ends), `cancel_at_period_end` resets to False
- Unit test: user with `cancel_at_period_end=True` sees cancellation message, not renewal message

### T3: Soft-Cap CTA Message
**Acceptance Criteria:**
- When subscriber quote count reaches `SOFT_CAP_THRESHOLD` (default 1000), the `/generate` response includes a CTA: "You've used {count} of {threshold} quotes this year. Need more? Contact us for custom pricing." with a `mailto:support@windowquoting.com` link
- CTA appears in the existing soft-cap notice block (Sprint 1 T3 already renders this block) — add the CTA text and link
- CTA only appears for subscribers at or above the threshold; non-subscribers see the existing "Buy Credits" prompt
- Unit test: subscriber with quote_count >= 1000 sees CTA in response

### T4: Pricing Page UI — All Tiers
**Acceptance Criteria:**
- Pricing card displays all 4 tiers side-by-side (mobile: stacked)
- Starter/Pro/Studio show "Buy Credits" → existing `/checkout` flow (no changes needed to the payment path)
- Unlimited shows "Subscribe" → existing annual checkout (no changes needed)
- Active tier highlighted for logged-in users
- Per-credit cost and discount percentage visible on each tier
- Responsive design (matches existing app theme)

### T5: Documentation + Sprint 1-2 Changelog
**Acceptance Criteria:**
- Update `CLAUDE.md` with pricing architecture, cancel-at-period-end flow, and soft-cap CTA
- Create `CHANGELOG.md` covering Sprint 1 (subscription tier) and Sprint 2 (pricing update, cancel UX, soft-cap CTA)
- Update `config.py` comments with new pricing rationale
- Document `cancel_at_period_end` column in data model reference

---

## Out of Scope
- Rate limiting / quote throttling (Sprint 3)
- Free tier credits beyond the existing `STARTING_CREDITS=5` (Sprint 3)
- Custom cap intake form (Sprint 3)
- Account security improvements (Sprint 3)
- Pre-created Stripe Products/Prices (current inline approach works fine)