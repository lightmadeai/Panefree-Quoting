---
sprint: 2
project: window-quoting
audit_type: post-audit
audited_by: Inquisitor
verdict: PASS
created: 2026-05-03
---

# Sprint 2 Post-Audit — Pricing Update + Cancel UX + Soft-Cap CTA

**Verdict: PASS** ✅

All 5 tasks meet their acceptance criteria. Implementation is clean, no drift from the manifest, and two execution decisions are improvements over spec. 3 non-blocking findings noted.

## Task-by-Task Review

### T1: Pricing Update in Config + Templates ✅
- `CREDIT_PACKS` in `config.py`: Starter 899/10, Pro 3900/50, Studio 6900/100 — matches manifest
- `ANNUAL_SUBSCRIPTION`: price_cents=17900, interval="year" — matches manifest
- `SOFT_CAP_THRESHOLD`: default 1000 (env-overridable) — matches manifest
- `top_up.html`: prices derived from config via Jinja math (`credit_packs.starter.price_cents / 100.0 / credit_packs.starter.credits`) — not hardcoded
- `$179/yr` Annual sticker price is the one legitimate hardcode (marketing copy)
- Discount percentages derived dynamically: 13% off Starter (Pro), 23% off Starter (Studio), 97%+ off Starter (Annual)
- Test: `CREDIT_PACKS["starter"]["price_cents"] == 899`, `ANNUAL_SUBSCRIPTION["price_cents"] == 17900` — passing

**Bonus over spec:** `index.html` correctly identified as not having pricing values to update (it's the quote generator, not the pricing page). Claude noted this in execution notes rather than blindly touching it.

### T2: Cancel-at-Period-End UX ✅
- `cancel_at_period_end` column on User model: `db.Column(db.Boolean, nullable=False, default=False)` — correct
- Migration in `_ensure_table_columns`: `("cancel_at_period_end", "BOOLEAN NOT NULL DEFAULT 0")` — idempotent, backfills existing rows to 0
- `_handle_subscription_updated`: mirrors `cancel_at_period_end` from Stripe **unconditionally** — handles both cancel-schedule AND re-activation (undo cancel via Billing Portal sends the same event with flag=False). This directly addresses pre-audit remark R2.
- `_handle_subscription_deleted`: resets `cancel_at_period_end = False` — correct for the terminal state
- Account template: `{% if current_user.cancel_at_period_end %}Cancels on:{% else %}Renews on:{% endif %}` — correct
- Nav badge: `Unlimited · {% if cancel_at_period_end %}cancels{% else %}renews{% endif %}` — correct
- Test: 3 unit tests covering renewing subscriber, cancel-pending subscriber, and nav verb swap — all passing

**Bonus over spec:** Manifest specified only the account section verb swap. Claude extended the same logic to the nav badge, which is the correct behavior — saying "renews" while a cancel is scheduled would be misleading.

### T3: Soft-Cap CTA Message ✅
- `notices.py`: new pure-Python module with `build_soft_cap_notice(quote_count, threshold, contact_email)` — returns `None` below threshold, structured payload at/above
- Threshold comparison uses `>=` (adopting "reaches" semantics from manifest, not strict `>`)
- CTA includes: count, threshold, message text, contact_email, contact_url (mailto:)
- `SUPPORT_EMAIL` config var: env-overridable, defaults to `support@windowquoting.com`
- `app.py` `/generate`: calls `build_soft_cap_notice()` and includes in response when `is_subscriber` and notice is not None
- Test: 4 unit tests (below threshold → None, at threshold → CTA, above threshold → CTA, edge case threshold=0) — all passing

**Bonus over spec:** `notices.py` is a separate pure-Python module, not embedded in `app.py`. This matches the project's existing pattern (`engine.py`, `generator.py`) and makes testing clean. `SUPPORT_EMAIL` is env-overridable, not hardcoded — better for test/staging.

### T4: Pricing Page UI — All Tiers ✅
- 4-tier grid: Starter / Pro / Studio / Annual Unlimited
- Per-credit cost derived dynamically from config (Jinja math), not hardcoded
- Discount percentages derived dynamically (`(1 - per_credit / starter_per_credit) * 100 | round | int`)
- "97%+ off Starter" is the one hardcode on the Annual card — matches manifest's marketing copy
- Mobile stacks (1 col), tablet 2x2, desktop 4 across — responsive
- Non-subscribers see all 4 tiers with Buy Credits / Subscribe buttons
- Active subscribers see "Annual Unlimited Active" banner + "Manage subscription" — grid hidden
- Past-due subscribers see grid with Annual card highlighted "Your plan — past due" + "Reactivate"
- Pro card gets `ring-2 ring-blue-500` (Most Popular badge)
- Test: 4 unit tests covering non-subscriber, active subscriber, past-due subscriber, simulator mode — all passing

**Bonus over spec:** Past-due subscriber gets a targeted "Reactivate" CTA on the Annual card — not in manifest, but correct UX. The manifest said "Active tier highlighted for logged-in users" without specifying past-due, and Claude's implementation covers this edge case.

### T5: Documentation + Sprint 1-2 Changelog ✅
- `CHANGELOG.md` created with Sprint 1 and Sprint 2 sections
- `CLAUDE.md` updated with: pricing architecture, subscription lifecycle, data model reference (all 4 subscription columns), cancel-at-period-end flow, quirks section
- `config.py` comments rewritten with pricing economics ladder
- `cancel_at_period_end` documented in both `models.py` docstring and `CLAUDE.md` data model table
- No separate DATA_MODEL doc (correct — project doesn't have one, documentation lives in CLAUDE.md)

## Definition of Done Verification

| Criterion | Status |
|-----------|--------|
| CREDIT_PACKS updated to new pricing | ✅ Starter 899/10, Pro 3900/50, Studio 6900/100 |
| ANNUAL_SUBSCRIPTION updated to $179/yr | ✅ 17900 cents |
| SOFT_CAP_THRESHOLD default changed to 1000 | ✅ Env-overridable, default 1000 |
| Templates display new pricing | ✅ Derived from config, not hardcoded |
| `/checkout` creates correct Stripe sessions | ✅ No changes to checkout logic (inline price_data pattern) |
| Unit test: pricing constants | ✅ 5 tests, all passing |
| `cancel_at_period_end` column added | ✅ Boolean NOT NULL DEFAULT 0, idempotent migration |
| Webhook mirrors cancel_at_period_end flag | ✅ Unconditionally — handles both cancel and re-activation |
| Account shows "Cancels on" when flag True | ✅ Verified in template |
| Nav badge shows "cancels" when flag True | ✅ Bonus — not in manifest, correct behavior |
| Flag resets on sub deletion | ✅ `_handle_subscription_deleted` sets False |
| Unit test: cancel UX | ✅ 3 tests, all passing |
| Soft-cap CTA at threshold 1000 | ✅ `>=` comparison, structured payload |
| CTA includes mailto link | ✅ `mailto:` + env-overridable `SUPPORT_EMAIL` |
| CTA only for subscribers | ✅ Gated on `is_subscriber` in `/generate` |
| Unit test: soft-cap CTA | ✅ 4 tests, all passing |
| 4-tier pricing page | ✅ Responsive, derived pricing, all user states |
| Active tier highlighted for logged-in users | ✅ Past-due gets "Your plan — past due" + Reactivate |
| Per-credit cost and discount % visible | ✅ Dynamically derived |
| Responsive design | ✅ Mobile/tablet/desktop breakpoints |
| Unit test: pricing page | ✅ 4 tests, all passing |
| CLAUDE.md updated | ✅ Pricing architecture, subscription lifecycle, data model |
| CHANGELOG.md created | ✅ Sprint 1 + Sprint 2 sections |
| config.py comments updated | ✅ Pricing economics ladder |
| cancel_at_period_end documented | ✅ models.py docstring + CLAUDE.md data model table |
| Sprint manifest in `done/` | ✅ |
| Sprint notes created | ✅ |
| `py_compile` on all modified files | ✅ Clean |
| 16 unit tests passing | ✅ |

## Findings (Non-Blocking)

### F1: 🟢 LOW — Manifest listed `index.html` as pricing update target
Manifest T1 acceptance criteria mentioned `index.html` as a template to update. Execution notes correctly identified that `index.html` has no pricing values (it's the quote generator). Not a functional issue — Claude did the right thing by not touching it.

### F2: 🟢 LOW — `SOFT_CAP_THRESHOLD` env var change only affects new deployments
Existing deployments with `SOFT_CAP_THRESHOLD=500` in environment keep 500 until the env var is updated. This is correct behavior (env vars should be sticky), but deployers should be aware. Documented in CHANGELOG.md migration notes.

### F3: 🟢 LOW — "97%+ off Starter" is hardcoded marketing copy
The Annual card's discount text is hardcoded as "97%+ off Starter" rather than derived from config. This matches the manifest's marketing copy exactly. When pricing changes, this text must be manually updated. Acceptable — it's marketing copy, not a calculation.

## Pre-Audit Remarks Follow-Up

| Remark | Resolution |
|--------|-----------|
| R1 (CTA email placeholder) | `SUPPORT_EMAIL` is env-overridable with default `support@windowquoting.com`. Production deploy must verify this domain. |
| R2 (Cancel re-activation) | ✅ Explicitly handled: `cancel_at_period_end = bool(sub.get("cancel_at_period_end"))` mirrors flag unconditionally. Re-activation sends the same webhook with flag=False. |
| R3 (SOFT_CAP_THRESHOLD env-only) | ✅ Correct — documented in CHANGELOG.md migration notes. |

## Summary

Sprint 2 ships clean. No drift from the manifest. Two execution decisions (nav badge verb swap, `notices.py` extraction) are improvements over spec. Re-activation edge case from pre-audit R2 is explicitly handled with unconditional flag mirroring. All 16 unit tests pass.

**Verdict: PASS** — No contested items. Sprint 2 is cleared for merge.