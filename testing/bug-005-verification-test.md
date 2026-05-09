# BUG-005 Re-Test — Email Verification Gate

**Sprint:** Hotfix-1 (Stabilize Phase) — T1
**Date:** 2026-05-09 03:06 UTC
**Driver:** `testing/bug_005_verification_test.py`
**Overall verdict:** **PASS ✅**

## Setup
- `.env` set with `SUPPORT_EMAIL=test-support@hotfix1.local` (satisfies T1 acceptance criterion).
- Driver boots a fresh app instance against an isolated temp sqlite DB (no pollution of `sovereign.db`).
- Verification email is logged via `[EMAIL-VERIFICATION]` (no real SMTP plumbing in scope this hotfix; the gate logic is what's being re-tested).

## Steps

### ✅ Step 1: register POST /register
- **Expected:** 302 redirect (auto-login -> /)
- **Actual:** 302
- **location:** `/`

### ✅ Step 2: verification URL logged via [EMAIL-VERIFICATION]
- **Expected:** log line containing the user's email + verify URL
- **Actual:** found
- **log_excerpt:** `[EMAIL-VERIFICATION] new user bug005-retest@hotfix1.local — verify URL: http://localhost/verify/a2118b0fd4c94b7bb51b73183bc5fc13`

### ✅ Step 3: DB row created with email_verified=False + token present
- **Expected:** email_verified=False, token=<32-hex>
- **Actual:** email_verified=False, token_len=32

### ✅ Step 4: POST /generate (unverified) -> 403 EMAIL_NOT_VERIFIED
- **Expected:** status=403, code=EMAIL_NOT_VERIFIED
- **Actual:** status=403, code=EMAIL_NOT_VERIFIED
- **message:** `Verify your email address before generating quotes. Check the verification link from your registration email.`

### ✅ Step 5: GET /verify/<token> -> 302 redirect (verified)
- **Expected:** 302 redirect to /
- **Actual:** 302 -> /

### ✅ Step 6: DB row reflects verification (flag flipped, token cleared)
- **Expected:** email_verified=True, token=None
- **Actual:** email_verified=True, token=None

### ✅ Step 7: create default profile (BUG-003 prereq for /generate success)
- **Expected:** 200/201 success
- **Actual:** 200

### ✅ Step 8: POST /generate (verified, with profile) -> 200 success
- **Expected:** status=200, body.status=success, file=quote_*.pdf
- **Actual:** status=200, body.status=success, file=quote_f82ad0.pdf
- **quote_id:** `1`
- **credits_remaining:** `9`

## Conclusion
BUG-005 (email verification gate) is verified working end-to-end. Unverified users are blocked from `/generate` with `403 EMAIL_NOT_VERIFIED`; clicking the verification link flips the flag and `/generate` then succeeds with `200`.

**Backlog status:** P2 — BUG-005 → can be checked off in `PLANNING/backlog.md`.
