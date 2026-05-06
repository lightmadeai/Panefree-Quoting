---
sprint: 2
project: window-quoting
audit_type: pre-audit
audited_by: Inquisitor
audit_status: rejected
created: 2026-05-03
---

# Sprint 2 Pre-Audit — Credit Bundle Tiers + Pricing Overhaul

**Verdict: REJECTED** ❌

5 blocking heresies found. Sprint 2 as drafted cannot proceed — it contradicts Sprint 1's shipped implementation in multiple ways and introduces scope that should not exist.

## Blocking Heresies

### 🚫 B1: Sprint 2 re-specifies what Sprint 1 already shipped
Sprint 1's `config.py` already has `CREDIT_PACKS` with Starter/Pro/Studio and `ANNUAL_SUBSCRIPTION`. The `/checkout` route already branches on `pack_id == "annual"` for subscriptions vs credit packs. Sprint 2 T1 ("DB Migration — Credit Bundle Fields") proposes adding `credit_balance` and `credit_tier` to the User model — **`credit_balance` already exists** (Sprint 0, `default=5`). Adding it again is a duplicate column migration that will fail.

**Remediation:** Remove T1 entirely. Credit bundles already work. If the pricing values need updating (see B3), that's a config change, not a migration.

### 🚫 B2: T2 re-implements Stripe checkout that already exists
`/checkout` already handles credit pack purchases via `mode="payment"`. T2 says "checkout session creates a one-time payment (not subscription) for bundles" — that's literally what the existing code does. T2 also says "three new Stripe Products/Prices" — but Sprint 1 uses inline `price_data` in checkout sessions, requiring no pre-created Products. Adding pre-created Price IDs is a different integration pattern and a regression from the existing approach.

**Remediation:** Remove T2. If the intent is to update pricing, see B3.

### 🚫 B3: Pricing conflict with shipped code
Sprint 2's table lists Starter at $8.99/10, Pro at $39/50, Studio at $69/100. But `config.py` currently has Starter $9.99/8, Pro $49/50, Studio $79/100. The notes in `sprint-1-notes.md` capture Chris's proposed revised pricing as a **parked item** — "Do not act on this during Sprint 1" — with explicit instruction that manifest values remain authoritative.

Sprint 2 cannot silently change these values without Chris's confirmed decision. The pricing change is real scope that needs a dedicated decision, not a task buried in a migration task.

**Remediation:** If Chris confirms the new pricing, create a separate sprint or task that updates `CREDIT_PACKS` and `ANNUAL_SUBSCRIPTION` in `config.py`. Do not bundle it with a migration that duplicates existing columns.

### 🚫 B4: T3 conflicts with Sprint 1's soft-cap design
Sprint 1's soft-cap is `SOFT_CAP_THRESHOLD` (default 500) — an **informational notice** on the `/generate` response, not a credit deduction system. Sprint 2 T3 says "Each quote request deducts 1 credit from `credit_balance`" and "Unlimited user at 800/1,000 credits sees softcap CTA message" — this implies Sprint 2 gives Unlimited users a 1,000-credit bucket and deducts from it.

**This directly contradicts Sprint 1's implementation**, where Unlimited subscribers bypass the credit reserve entirely. The `/generate` route has an explicit `is_subscriber` branch that skips `credit_balance` deduction. Re-introducing credit deduction for subscribers would re-introduce Heresy #12 (lapsed-but-cached subscriber risk) through a different vector.

**Remediation:** Remove credit deduction for Unlimited subscribers. The soft-cap is informational only — Sprint 1 already implements this correctly. If a new soft-cap threshold (1,000 vs 500) is desired, update `SOFT_CAP_THRESHOLD` env var.

### 🚫 B5: `credit_tier` enum is unnecessary schema bloat
T1 proposes `credit_tier` (enum: none/starter/pro/studio/unlimited) on the User model. This is redundant — the user's tier is derivable from their existing state: `subscription_status == "active"` → Unlimited, otherwise derive from `credit_balance` or last Transaction. Storing a denormalized tier column creates a new consistency heresy: what happens when `credit_tier` says "starter" but the user just bought a Pro pack? The tier must be updated on every purchase, creating a write path that can drift from the source-of-truth (Transaction history).

**Remediation:** Remove `credit_tier`. If tier display is needed in the UI, derive it from existing data at render time.

## Non-Blocking Remarks

### 🟡 R1: "Softcap CTA: Contact us for custom cap rates" — no backend specified
T3 mentions a CTA email link for custom cap rates, but Sprint 3 T3 has the actual intake form. Sprint 2 should not reference Sprint 3 features as acceptance criteria.

### 🟢 R2: Task count is 5 — at the cap
Sprint 2 has exactly 5 tasks (the maximum). Given that 3 of them (T1-T3) need removal or major revision, the actual scope is much smaller than the task count suggests.

### 🟢 R3: `depends_on: sprint-1-post-audit`
Correct dependency declaration. This audit IS that dependency.

## Recommended Path Forward

Sprint 2 needs a complete redraft. The core problem: it was drafted assuming Sprint 1 shipped "only the annual subscription" and that credit bundles needed to be built from scratch. In reality, **Sprint 0 already shipped credit bundles** and Sprint 1 layered the annual subscription on top of them. Sprint 2 should focus on:

1. **Pricing update** — If Chris confirms the revised tier table ($8.99/10, $39/50, $69/100, $179/yr), update `CREDIT_PACKS` and `ANNUAL_SUBSCRIPTION` in config
2. **UI improvements** — Pricing card redesign if the new pricing changes the visual layout
3. **Cancel-at-period-end UX** — The known gap from Sprint 1 (F4 in post-audit)
4. **Soft-cap threshold adjustment** — If 500 → 1000, that's a config change

This is likely a 2-3 task sprint, not 5.

**Verdict: REJECTED** — Redraft required before re-audit.