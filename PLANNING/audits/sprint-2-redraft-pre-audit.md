---
sprint: 2
project: window-quoting
audit_type: pre-audit (redraft)
audited_by: Inquisitor
audit_status: approved
created: 2026-05-03
---

# Sprint 2 Redraft Pre-Audit — Pricing Update + Cancel UX + Soft-Cap CTA

**Verdict: APPROVED** ✅

All 5 original blockers addressed. Redraft is clean, correctly references existing code, and introduces no heresies. 3 non-blocking remarks.

## Original Blocker Resolution

| # | Original Blocker | Resolution |
|---|-----------------|------------|
| B1 | Duplicate `credit_balance` column | ✅ Removed. Sprint acknowledges existing column |
| B2 | Re-implements Stripe checkout | ✅ Removed. T4 explicitly uses existing `/checkout` flow |
| B3 | Pricing conflict buried in migration | ✅ Now T1 — explicit config + template update |
| B4 | Credit deduction for Unlimited subscribers | ✅ Removed entirely. Sprint 2 doesn't touch `/generate` logic |
| B5 | `credit_tier` enum bloat | ✅ Removed. No mention of `credit_tier` anywhere |

## Task Review

### T1: Pricing Update in Config + Templates ✅
- Clear delta: Starter $9.99/8→$8.99/10, Pro $49/50→$39/50, Studio $79/100→$69/100, Annual $149→$179
- `SOFT_CAP_THRESHOLD` default 500→1000
- Falsifiable: `CREDIT_PACKS["starter"]["price_cents"] == 899` — testable
- Correctly targets config + templates, not a DB migration

### T2: Cancel-at-Period-End UX ✅
- New `cancel_at_period_end` Boolean column on User — addresses post-audit finding F4
- Webhook handler updated to set flag on `customer.subscription.updated`
- Account/Nav UI shows "Cancels on {date}" instead of "Renews on {date}"
- Resets to False when subscription fully cancels — correct
- Falsifiable: user with flag True sees cancellation message

### T3: Soft-Cap CTA Message ✅
- Adds CTA text + `mailto:` link to existing soft-cap notice block
- Only appears for subscribers at/above threshold
- No structural changes to `/generate` — just extends the existing `soft_cap_notice` block
- Falsifiable: subscriber with quote_count >= threshold sees CTA

### T4: Pricing Page UI — All Tiers ✅
- 4-tier display with existing checkout flows (no new payment logic)
- Active tier highlighting for logged-in users
- Per-credit cost and discount percentage visible
- Falsifiable: responsive design, correct pricing displayed
- Correctly states "no changes needed to the payment path"

### T5: Documentation + Sprint 1-2 Changelog ✅
- CLAUDE.md update, CHANGELOG.md creation, config comments, data model reference
- Falsifiable: files committed

## Protocol Compliance

| Criterion | Status |
|-----------|--------|
| ≤ 5 tasks | ✅ (5 tasks) |
| All acceptance criteria falsifiable | ✅ |
| No scope creep beyond "Why" | ✅ |
| Dependencies noted | ✅ (`depends_on: sprint-1-post-audit (PASS)`) |
| "What Already Exists" section | ✅ — explicitly lists what NOT to rebuild |
| Out of scope explicit | ✅ (5 items) |

## Non-Blocking Remarks

### 🟢 R1: CTA email is a placeholder
`mailto:support@windowquoting.com` in T3 — ensure this domain/email is actually set up before deploy. If it's a placeholder, document it. Sprint 3 T3 replaces this with a `/contact` page, so it's a temporary bridge.

### 🟢 R2: Cancel-at-period-end webhook edge case
T2 says "On `customer.subscription.updated`, if `cancel_at_period_end=True`, set user's `cancel_at_period_end=True`." But what about the reverse? If a customer *re-activates* after canceling (Stripe supports this), the `cancel_at_period_end` flag should be set back to `False`. The webhook handler should handle both transitions. The acceptance criterion "resets to False when subscription fully cancels" covers the end state, but re-activation is a different path.

**Recommendation:** In the webhook handler, explicitly set `cancel_at_period_end = False` when `cancel_at_period_end` is not present or False in the Stripe event. Don't rely on the deletion event alone to clear the flag.

### 🟢 R3: `SOFT_CAP_THRESHOLD` change is env-only
T1 changes the default from 500 to 1000. This only affects new deployments — existing deployments with `SOFT_CAP_THRESHOLD=500` in their environment will keep 500. This is correct behavior (env vars should be sticky), but Claude should note this in the changelog.

## Summary

Clean redraft. All blockers resolved. Sprint 2 correctly builds on Sprint 1's shipped code without duplicating it. Ready for execution.

**Verdict: APPROVED** — Ready for promotion to `current-sprint.md` after Sprint 1 merge.