# 🛡️ Project Audit Log: Window Cleaning Sovereign Engine
**Status**: Active
**Objective**: Document all "Heresies" and structural failures to ensure zero regression during the SaaS transition.

## 🚫 The "SaaS Transition" Audit (2026-04-21)

### Heresy #1: The Credit Race Condition
- **Failure**: Contradiction between Blueprint (charge first) and Port Guide (charge last).
- **Risk**: Loss of revenue (race condition) or user frustration (charge on failure).
- **Sovereign Fix**: Implemented "Reserve $\rightarrow$ Generate $\rightarrow$ Refund on Failure" pattern.
- **Status**: RESOLVED.

### Heresy #2: Database Schema Drift
- **Failure**: `total_recovered_value` logic was added to the app but the column was missing from the SQL schema.
- **Risk**: Runtime crashes upon first value recovery event.
- **Sovereign Fix**: Added `total_recovered_value DECIMAL DEFAULT 0` to the `users` table.
- **Status**: RESOLVED.

### Heresy # la: The Ghost Baseline
- **Failure**: Value recovery calculated against an undefined "standard rate."
- **Risk**: Hallucinated "savings" that don't reflect real-world profit.
- **Sovereign Fix**: Defined a global `BASELINE_RATE` constant in the config as the anchor for all recovery calculations.
- **Status**: RESOLVED.

## 🚫 The "Monetization & Profiles" Audit (2026-04-22)

### Heresy #3: The Replayed Webhook
- **Failure**: A naive webhook handler credits a user every time Stripe retries a delivery.
- **Risk**: Silent revenue loss via free credits on duplicate event delivery.
- **Sovereign Fix**: `transactions.stripe_tx_id` carries a UNIQUE constraint. Webhook flow inserts the transaction first; if it collides, the handler treats the event as already-processed and acks without re-crediting.
- **Status**: RESOLVED.

### Heresy #4: The Ghost Price Sheet
- **Failure**: After migrating pricing to the `pricing_profiles` table, `price_sheet.json` was still being read at runtime in places — creating two sources of truth that would silently diverge.
- **Risk**: A user edits their DB profile, but quotes still use the packaged JSON defaults.
- **Sovereign Fix**: `price_sheet.json` is now explicitly seed-only (config key `SEED_PRICE_SHEET_PATH`). All runtime reads go through `get_user_profile_registry(user)` which hits the DB. The legacy `/settings` route redirects to `/profiles`.
- **Status**: RESOLVED.

### Heresy #5: The Cross-Tenant Profile Leak
- **Failure**: Profile-lookup queries that don't filter by `user_id` would let a user set another user's profile as default, or quote from it.
- **Risk**: Data leak; violates the "every user has their own price sheet" contract.
- **Sovereign Fix**: Every `PricingProfile.query` in `app.py` is `.filter_by(user_id=current_user.id)`. Ownership is re-checked before any mutation (set-default, delete).
- **Status**: RESOLVED.

### Heresy #6: The Racing Default
- **Failure**: "Set as default" implemented as two separate UPDATEs can leave two profiles flagged `is_default=true` if a request is retried mid-flight.
- **Risk**: Ambiguous active profile; quote generation picks whichever row the DB returns first.
- **Sovereign Fix**: `set_default_profile()` wraps both UPDATEs in a single transaction and commits once — first clears all defaults for the user, then sets the new one, then commits.
- **Status**: RESOLVED.

## 🚫 The "Quote Archive & Invoice Conversion" Audit (2026-04-22)

### Heresy #7: The Invoice-Conversion Credit Bypass
- **Failure**: Invoice generation accepts arbitrary form data and routes through the same PDF path as quote generation, but is "free". A motivated user could submit every new job as an "invoice" and pay zero credits.
- **Risk**: 100% revenue loss on the entire product. Users never need to buy a credit pack after the initial free allotment.
- **Sovereign Fix**: `/generate` only produces QUOTE PDFs and is the *only* endpoint that decrements credits. Invoice/regeneration routes (`POST /quotes/<id>/pdf`) accept only a `quote_id` that points to an already-persisted Quote row. The stored snapshot is rehydrated and re-rendered — no recalculation, no form replay. Credit was paid at the time the underlying Quote was created; free re-renders of that immutable record are safe.
- **Status**: RESOLVED.

### Heresy #8: The Cross-Tenant Quote IDOR
- **Failure**: History/invoice/regeneration routes keyed by `quote_id` without a `user_id` filter let any authenticated user download, re-label, or re-invoice any other user's quote.
- **Risk**: Data leak; customer-label and pricing data exposed across tenants.
- **Sovereign Fix**: Every `Quote.query` in the controller is `.filter_by(id=..., user_id=current_user.id)`. Cross-tenant access returns 404. Covered by `test_cross_tenant_idor_blocked`.
- **Status**: RESOLVED.

### Heresy #9: The Benchmark Ghost Data
- **Failure**: The "internal mirror" averages $/pane across historical quotes, but profile rate changes, one-off overrides, and mixed job types make early samples misleading. A user with 1–3 quotes sees a "benchmark" that is actually just their first quote.
- **Risk**: False confidence in a meaningless reference point; worse, users start adjusting live quotes against noise.
- **Sovereign Fix**: Benchmark is gated behind `total_history > 3` AND a non-empty ±25% pane-count band. Rendered as a subtle, non-banner note. No margin/profit claims made from it. Engine stays pure — benchmark lives entirely in `app.py` and reads only the Quote table.
- **Status**: RESOLVED (with known limitation).

### Heresy #10: The Label Injection
- **Failure**: User-supplied customer/job labels flow into the PDF header and the DB unsanitized. Newlines, control chars, absurdly long strings, or emoji/CJK glyphs crash FPDF (helvetica is Latin-1 only) — and the crash happens *after* the credit reserve, triggering a refund cycle on every rogue label.
- **Risk**: Denial of PDF generation; silent user frustration; credit-balance churn from reserve/refund cycles.
- **Sovereign Fix**: Two-layer sanitize. Controller (`sanitize_label`) trims, collapses whitespace, caps at 80 chars, stores full unicode in the DB. Generator (`_sanitize_label`) additionally normalizes smart-quotes/dashes and encodes to Latin-1 with `errors="ignore"` so any remaining exotic glyph gets dropped before it reaches FPDF. Form input has `maxlength=80`.
- **Status**: RESOLVED.

### Heresy #11: The Orphaned Rehydration
- **Failure**: Calculation snapshots contain `Decimal` instances. Naive `json.dumps` on the snapshot either crashes or silently converts to `float`, so when an invoice is regenerated from storage the totals drift one cent below the original quote.
- **Risk**: Customer gets a quote PDF for $1,234.57 and later an invoice PDF for $1,234.56 — a legal/contract liability that will never surface in testing.
- **Sovereign Fix**: `_serialize_for_json` walks the snapshot recursively and converts every `Decimal` to its string representation before `db.JSON` persists it. `load_quote_snapshot` + `_rehydrate_decimals` round-trips those strings back to `Decimal` on read. Covered by `test_lossless_decimal_roundtrip`.
- **Status**: RESOLVED.

---
**Sovereign Directive**: Any future implementation must check this log before finalizing code to ensure previous heresies are not reintroduced.
