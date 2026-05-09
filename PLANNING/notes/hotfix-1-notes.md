# Hotfix-1 Execution Notes

**Started:** 2026-05-08
**Branch:** `hotfix-1` (from master @ 32609f3)
**Phase:** Stabilize
**Manifest:** `PLANNING/sprints/HOTFIX_1_MANIFEST.md`
**Pre-audit:** `PLANNING/audits/hotfix-1-pre-audit.md` (CONDITIONAL PASS)

## Pre-execution status correction
- `current-sprint.md` had `audit_status: pending` despite Inquisitor pre-audit verdict CONDITIONAL PASS being on file. Flipped to `approved` with `audit_note` recording the correction.

## Inquisitor non-blocking remarks (carried in)
- **R1 (T2):** Current `PERMANENT_SESSION_LIFETIME` is `timedelta(hours=24)`, not 31 days as manifest says. Change is `24h → 7d`.
- **R2 (T2):** Keep `_session.permanent = True` — Flask requires it for `PERMANENT_SESSION_LIFETIME` to apply.
- **R3 (T3):** `.gitignore` already includes `output/` (line 17) and `*.bak`/`*.bak-*` (lines 25-26 from Sprint 4 docs commit). Sprint 4 BUG-008 already routes new PDFs to `output/quotes/<user_id>/`. Migration script is for legacy PDFs at project root.
- **R4 (T5):** Refund is symmetric in rollback handler (lines 1029-1031). Risk of failed refund after rollback exists but is low. Add try/except + comment.
- **R5 (T4):** `sanitize_label` confirmed at lines 865, 972 (quote labels, contact labels). Need to audit profile settings + other free-text entries.

## Task progress
- [x] T1: Email verification gate re-test — `testing/bug_005_verification_test.py` driver + `testing/bug-005-verification-test.md` report; 8/8 steps PASS (register→403→verify→200 path verified end-to-end)
- [x] T2: Session lifetime → 7 days — `PERMANENT_SESSION_LIFETIME = timedelta(days=7)` moved into `config.py` (was hard-coded in `app.py` at 24h). `app.config.from_object(config)` picks it up. Both `/register` and `/login` carry an explicit `# DO NOT REMOVE` comment on `_session.permanent = True`. Verified: session cookie `Expires` is exactly 7 days after login (delta within ms tolerance).
- [x] T3: Legacy PDF migration script — `scripts/migrate-pdfs.py` (idempotent, dry-run flag). Confirmed: 137 legacy PDFs at project root → `output/_legacy_unattributed/`; second run is a no-op. Path correction: code uses `OUTPUT_DIR/<user_id>/`, NOT `OUTPUT_DIR/quotes/<user_id>/` as manifest states (manifest wording is wrong; the BUG-008 fix in Sprint 4 set the actual layout). Migration script does NOT attribute to users — Quote table never persisted the rendered filename, so deterministic per-user mapping is impossible. DEPLOYMENT.md §2.5 added (output/ setup + migration script invocation), §2.6/2.7 renumbered. .gitignore already covered `output/` (line 17) and `*.bak` / `*.bak-*` (lines 25-26 from Sprint 4 commit) — no change needed.
- [x] T4: Input sanitization audit — driver `testing/input_sanitization_audit.py` + report `testing/input-sanitization-audit.md`. 16/16 checks PASS. Closed gaps at `/account` (business_name, phone_number), `/contact` (all 4 fields), `/profiles/new` and `/api/profiles/create` (name on both routes). New constants `BUSINESS_NAME_MAX=200`, `PROFILE_NAME_MAX=80`, `CONTACT_COMPANY_MAX=200`, `CONTACT_VOLUME_MAX=200`, `CONTACT_GROWTH_MAX=2000`, `CONTACT_EMAIL_MAX=254`. Found pre-existing test failure unrelated to T4 changes — `test_soft_cap_cta_points_at_contact_route` (predates BUG-003 auto-seed removal); added to backlog.
- [x] T5: Credit refund atomicity — wrapped the symmetric refund (app.py:~1029) in try/except. Failure mode: rollback the refund attempt, log `[CREDIT-REFUND-FAILED]` with original + refund errors for manual reconciliation, still return the 400 from the original error. No retry (a same-request retry blocks on the same flake; queued retry is over-engineered for credit accounting). Driver `testing/credit_refund_atomicity_test.py` covers two scenarios: happy refund (engine raises → balance restored) and refund-failure (engine raises AND refund UPDATE raises → 400 not 500, log line present). Both PASS.

## Decisions / Deferrals
_(append as work proceeds)_

## Open questions
_(none yet)_
