---
label: hotfix-1
project: window-quoting
phase: stabilize
drafted_by: Jade
status: ready
created: 2026-05-06
audit_status: pending
---

# Hotfix-1 — Email Verification + Deployment Polish

## Why
Sprint 4 fixed all P0/P1 bugs. The remaining items are P2 hardening and deployment readiness gaps that need to be closed before we can ship. This hotfix tackles the most impactful ones.

## Tasks

### T1: Verify Email Verification Gate (BUG-005 re-test)
**Acceptance Criteria:**
- Set `SUPPORT_EMAIL` in `.env` (test value is fine)
- Register a new account — verify that the verification email sends and `/generate` returns 403 `EMAIL_NOT_VERIFIED` until the user clicks the link
- Verify that after clicking the verification link, `/generate` returns 200
- Document test results in `testing/bug-005-verification-test.md`

### T2: Session Lifetime Hardening (OBS-003)
**Acceptance Criteria:**
- Set `PERMANENT_SESSION_LIFETIME = timedelta(days=7)` in `config.py` (changes default from 24h to 7 days)
- Verify login session expires after 7 days (check by inspecting session cookie expiry in browser dev tools)
- Keep `_session.permanent = True` in login/register routes — it IS required for `PERMANENT_SESSION_LIFETIME` to take effect. Add explanatory comment: `# DO NOT REMOVE — required for PERMANENT_SESSION_LIFETIME to apply`
- Verify that session cookie reflects the 7-day expiry after login

### T3: Legacy PDF Migration + Output Directory
**Acceptance Criteria:**
- Create `output/quotes/<user_id>/` directory structure for new PDFs (already implemented by Sprint 4 BUG-008 fix — verify path)
- Write a one-time migration script `scripts/migrate-pdfs.py` that moves any existing PDFs from `project_root/` to the new `output/quotes/<user_id>/` structure
- Migration script is idempotent (safe to run multiple times)
- Add `output/` directory setup to `DEPLOYMENT.md` as a deployment step
- Verify `.gitignore` includes `output/` and `*.bak` files

### T4: Input Sanitization Audit (BUG-009 follow-up)
**Acceptance Criteria:**
- Audit all form entry points (quote form, profile settings, contact form) for server-side length caps
- Confirm `sanitize_label` covers all customer-facing text fields
- Add server-side length validation for any fields that lack it (max 500 chars for labels, max 2000 for notes/descriptions)
- Test with oversized inputs — verify they're truncated or rejected with clear error messages
- Document results in `testing/input-sanitization-audit.md`

### T5: Credit Refund Atomicity (OBS-002)
**Acceptance Criteria:**
- Wrap the credit refund in a try/except within the same DB transaction as the quote rollback
- If the refund UPDATE fails, log the error but don't crash — the quote generation already failed, so the user's credit should still be intact
- Add a comment explaining the retry/failure strategy
- Test: manually simulate a DB lock during quote generation (or add a test mode flag) and verify credits are preserved

---

## Out of Scope
- Alembic migration tooling (Ops tier — pull after P2s clear)
- Live Stripe key swap (Ops tier)
- HTTPS enforcement (Ops tier)
- Production deployment (Ops tier)
- Visual QA (requires Chris)
- Monitoring/alerting (Ops tier)

## Notes
- Window Quoting is now in Stabilize Phase per §13 of PLANNING-PROTOCOL.md
- Branch from master (Sprint 4 merge)