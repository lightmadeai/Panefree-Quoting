# Sprint 2 Execution Notes

Started: 2026-05-03 (Claude Code, branch `sprint-2`, base `sprint-1` HEAD)

Sprint 1 has not yet merged to master; sprint-2 branches from sprint-1 since
the manifest depends on Sprint 1's code (annual sub, soft-cap, reserve bypass).

## Decisions / deferrals

**T1 — manifest cited `index.html` as a pricing-update target.** It has no pricing values to update (it's the quote-generator UI). All credit-pack prices in templates derive from `pack.price_cents` via Jinja math; the only hardcoded price string was `$149` in [top_up.html:57](templates/top_up.html), which is now `$179`. config.py's comment block also rewritten with the new economics ladder.

**T2 — UNIQUE-style migration constraints don't apply to BOOLEAN.** Unlike `subscription_id` (Sprint 1), `cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0` is a one-step ALTER TABLE in SQLite — backfills existing rows to 0, idempotent under `_ensure_table_columns`'s PRAGMA-guarded re-runs. Verified against a simulated sprint-1-shipped users table.

**T2 — nav verb swap is a bonus.** Manifest specifies the account-section "Cancels on / Renews on" swap; nav was specified only as "still shows 'Unlimited' during the active period". I extended the same verb swap to the nav badge ("Unlimited · cancels YYYY-MM-DD" vs "Unlimited · renews YYYY-MM-DD") since saying "renews" while a cancel is scheduled is wrong even if the badge stays emerald-colored. Surface for post-audit review.

**T3 — soft-cap threshold semantics tightened from `>` to `>=`.** Sprint 1 manifest said "exceeds 500"; Sprint 2 manifest says "reaches 1000". Adopted `>=` which matches "reaches" and is the natural reading of "at or above". Captured as part of the visible delta.

**T3 — soft-cap CTA factored into `notices.py` (new file).** Pure-Python helper kept outside `app.py` so the unit test doesn't have to boot Flask + the database. Matches the project's existing pattern of pure modules (`engine.py`, `generator.py`) vs. the Flask layer in `app.py`. Adds a 22-line file; the test for it is a clean 4 cases.

**T3 — `SUPPORT_EMAIL` config added as the CTA target.** Manifest hardcodes `support@windowquoting.com`; I made it env-overridable so test/staging can route the conversation elsewhere without a redeploy. Default matches the manifest.

**T4 — past-due users see Annual highlighted as "Your plan — past due" with a "Reactivate" button.** Manifest says "Active tier highlighted for logged-in users". Active subscribers already see the banner and never reach the grid; the only logged-in users on `/top-up` who could use a tier highlight are past_due. For non-subscribers I left the existing badges (Pro = Most Popular, Annual = Best Value) — those are the implicit recommendations.

**T4 — discount % computed from configured prices.** Per-credit cost and "X% off Starter" are derived in the template from `CREDIT_PACKS[].price_cents / .credits` rather than hardcoded — when a future sprint reprices, the percentages update automatically. Annual's "97%+ off Starter" is hardcoded text matching the manifest's marketing copy (the actual math depends on assumed usage).

**T5 — no separate DATA_MODEL doc.** Manifest asked for "Document `cancel_at_period_end` column in data model reference". The project has no standalone data model file; documented in CLAUDE.md's new "Data model — subscription columns on `users`" table covering all four subscription columns added across Sprints 1+2. Models.py docstring on the column itself remains the in-code reference.

## Verification performed

- `python -m py_compile` on all modified `.py` files: clean.
- 16 unit tests in `test_sprint2.py` pass (5 pricing constants, 3 cancel-at-period-end UX, 4 pricing-page grid, 4 soft-cap CTA payload).
- Sprint-2 migration tested in isolation against a sprint-1-shipped users schema — `cancel_at_period_end` adds with default 0, existing rows preserved, PRAGMA-guarded re-run is a no-op.
- Dev server (already running from end of Sprint 1, debug auto-reload) survived all edits; `/login` 200, `/top-up` 302 (login-redirect — expected when unauthenticated).
- Jinja templates render with `StrictUndefined` against {non-subscriber, active, past_due, canceled} × {real Stripe, simulator}.

## Open questions surfaced during execution

(none — implementation followed manifest. Manifest's "## Open questions" was empty.)

