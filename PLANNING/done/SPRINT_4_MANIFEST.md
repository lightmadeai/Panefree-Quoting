---
sprint: 4
project: window-quoting
drafted_by: Jade
status: done
created: 2026-05-05
depends_on: sprint-3-completion
audit_status: approved
audit_note: Redrafted 2026-05-06 to rebalance task weight. Carry-forward from May 3 pre-audit applies to T2-T5 scope. T1 split and respecified based on sprint-4-notes.md findings.
---

# Sprint 4 — Code-Side Ship Readiness

## Why
Sprints 1-3 shipped all features. Manual walkthrough and stress testing (documented in `sprint-4-notes.md`) revealed 8 bugs and 3 observations. Sprint 4 fixes the critical issues, hardens the application, and prepares deployment documentation — everything Claude can do and verify without live infrastructure.

## Tasks

### T1: Critical Security + Core Bug Fixes
**Acceptance Criteria:**
- **BUG-008 (P0):** Fix `/download/<filename>` route (`app.py:931-935`) — restrict to PDF files owned by the requesting user. Move generated PDFs to `quotes/<user_id>/` subdirectories. Validate resolved path falls within the caller's directory. Verify `sovereign.db`, `app.py`, `config.py`, `models.py` are no longer downloadable by any authenticated user.
- **BUG-006 (P1):** Fix "(Custom Rate)" on all line items — change `templates/index.html:203-205` to use `placeholder` instead of `value` for `override_floor1/2/3`. When user accepts defaults, no override values are submitted, and the engine uses computed rates.
- **BUG-002 (P1):** Update signup copy from "5 free quote credits" to "10 free quote credits" to match `STARTING_CREDITS = 10`. Search for all occurrences of "5 free" across templates.
- **Soft-cap frontend removal:** Remove soft-cap threshold display from `top_up.html` pricing card (line 121). Pricing card must say only "Unlimited quotes" with no threshold shown. `soft_cap` variable still passes in context for active-subscriber banner logic but is NOT rendered on the pricing card.
- **80% soft-warning tier:** Add `build_soft_cap_warning` function in `notices.py` — at 80% of `SOFT_CAP_THRESHOLD` (800 quotes default), return `soft_cap_warning` payload with message "You've used 800+ quotes this year. We'll reach out if you need volume pricing." Non-blocking, no CTA. Existing `soft_cap_notice` at 100% unchanged.
- Each fix includes a brief note in `sprint-4-notes.md` explaining root cause and fix
- Zero P0 bugs remaining at end of sprint

### T2: UX Flow Fixes
**Acceptance Criteria:**
- **BUG-003 (P1):** Remove starter profiles on signup. New users start with zero profiles. Route new users to account/profile page on first login (not `/generate`). Implement a `first_login` flag on `User` model or check profile count on login.
- **BUG-004 (P1):** Persist quote form data when user navigates to buy credits mid-quote. Use `sessionStorage` to save form values on navigation away from `/generate`, restore on return, clear after successful quote generation.
- **BUG-007 (P2):** Add sequential display IDs for quotes (e.g., `Q-000001`). Keep random slug for URLs/files. Add `next_quote_number` and `quote_prefix` (default `Q-`) to `User` model. Update quote PDF rendering and history list to show sequential number. On quote→invoice conversion, carry sequential number forward (Q-000001 → INV-000001).

### T3: Programmatic Stress Test + Verification
**Acceptance Criteria:**
- Run `testing/stress_probe.py` against the dev server after all T1/T2 fixes are applied
- Verify BUG-008 fix: attempt `/download/sovereign.db` and `/download/app.py` — must fail (403 or 404)
- Verify BUG-006 fix: generate a quote with default values — line items show computed prices, not "(Custom Rate)"
- Verify BUG-002 fix: signup page copy says "10 free quote credits"
- Verify 80% soft-warning tier: generate 800+ quotes as annual subscriber, verify `soft_cap_warning` in response
- Verify 100% soft-cap CTA still fires at threshold
- Verify rate limiting (10/hr free, subscriber bypass)
- Verify cancel-at-period-end flow
- Verify email verification gate
- Create standalone `testing/stress-test-results.md` documenting all results

### T4: Deployment Documentation + Environment Templates
**Acceptance Criteria:**
- Create `DEPLOYMENT.md` with step-by-step production deployment guide: environment variables, Stripe key rotation, HTTPS enforcement, database backup, webhook configuration
- Create `.env.example` with all required variables documented (no real secrets)
- Generate a cryptographically random `SECRET_KEY` placeholder in `.env.example` with a comment explaining how to generate a real one
- Document which env vars must be set for live mode vs test mode (especially `DEV_MODE`, `STRIPE_*`, `APP_BASE_URL`)
- Document BUG-001 schema parity lesson: run schema check against model before deploy, consider Alembic for future migrations
- Verify `PROJECT.md` and `CLAUDE.md` are current and accurate for Sprint 4 scope

### T5: Final Polish + Release Documentation
**Acceptance Criteria:**
- Remove all `console.log` / `print` debug statements from production code
- Wire `SUPPORT_EMAIL` env variable, referenced in templates (not hardcoded)
- Add contact email (`support@<domain>`) to: site-wide footer, account/settings page, error pages (404, 500), soft-cap CTA
- Verify `/contact` form persists submissions to DB
- Verify soft-cap CTA email link routes to `/contact`
- Write `RELEASE_NOTES.md` covering v1.0 features across Sprints 1-4, including soft-cap UX change
- Write `CHANGELOG.md` entries through Sprint 4
- Both documents are publication-ready (no TODOs, no placeholders, accurate version references)

---

## Out of Scope (moved to Sprint 5 / post-stabilization)
- Live Stripe key swap and real-card testing
- HTTPS enforcement (infrastructure config)
- Production deployment (live environment)
- Manual visual QA (requires human eyes)
- Monitoring/alerting setup
- DB backup (one-time operational action)
- SEO / marketing landing page

## Notes
- Sprint 3 is already merged to master (commit `0e43594`). Sprint 4 branches from master cleanly.
- Bug findings and stress test results are in `sprint-4-notes.md` — this is input to the sprint, not output.
- BUG-001 (orphan `total_recovered_value` column) was fixed manually during walkthrough by dropping the column from SQLite. No code change needed, but document the schema parity lesson in DEPLOYMENT.md (T4).
- BUG-005 (email verification gate) is blocked on T5's `SUPPORT_EMAIL` wiring. Re-test after T5.
- BUG-009 (unicode/oversize inputs) and OBS-002/003 are P3/defense-in-depth — out of scope for this sprint, flagged for future hardening.