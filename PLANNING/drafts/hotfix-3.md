---
label: hotfix-3
project: window-quoting
phase: stabilize
drafted_by: Claude (proposal), Jade (adoption with Inquisitor conditions)
adopted_by: Jade
status: ready
audit_status: pre-approved (conditional)
created: 2026-05-12
depends_on: hotfix-2 (merged)
inquisitor_conditions:
  C1: "/resend-verification is logged-in-only — no email param (enumeration risk)"
  C2: "Account deletion is hard delete with audit log, not soft delete (GDPR compliance, Stripe holds billing records)"
  C3: "Postmark confirmed for v1 — best deliverability, simplest setup, 100/mo free tier"
---

# Hotfix-3 — User Access Lifecycle: Email + Reset + Account Deletion

## Why

The product is currently unusable end-to-end. `/register` "sends" the
verification email via `app.logger.info("[EMAIL-VERIFICATION] ...")` —
no real delivery — so new users can never satisfy the `email_verified`
gate that blocks `/generate`. There is also no password reset flow
(forgotten password = locked out permanently) and no account deletion
(GDPR/CCPA exposure + Stripe live-mode rejects merchants without one).
These three gaps must close before launch.

## Goals

- New users receive a real verification email within seconds of registration
- Users who forget their password can recover their account without contacting support
- Users can self-serve account deletion, including Stripe subscription cancellation
- All transactional emails flow through a single backend so deliverability + observability live in one place

## Inquisitor Conditions (RESOLVED)

- **C1:** `/resend-verification` → **logged-in-only**. No email parameter. The resend link appears in the EMAIL_NOT_VERIFIED banner visible only to authenticated unverified users.
- **C2:** Account deletion → **hard delete with audit log**. GDPR Article 17 requires erasure without undue delay. `deleted_at` soft-delete is a compliance liability unless justified by legitimate interest. `[ACCOUNT-DELETED]` audit log provides the trail. Stripe holds canonical billing records.
- **C3:** **Postmark confirmed.** Transactional-only, 100/mo free tier, best deliverability reputation. SES requires DNS-heavy setup; SendGrid has worse deliverability on free tier. Revisit only if volume exceeds Postmark pricing thresholds.

## Tasks

### T1: Email backend integration (Postmark)
**touches:** new `mailer.py`, `requirements.txt`, `config.py`, `.env.example`
**acceptance:**
- New `mailer.send_email(to, subject, html_body, text_body)` helper using
  Postmark's HTTP API (NOT SMTP — fewer auth headaches, better deliverability
  tracking).
- `POSTMARK_SERVER_TOKEN`, `EMAIL_FROM`, `EMAIL_FROM_NAME` env vars added;
  missing token raises at boot in non-DEV_MODE, logs warning in dev.
- New `MAIL_DISABLED=1` env (matching the WTF_CSRF_DISABLED / RATELIMIT_DISABLED
  pattern from Hotfix-2): when set, `send_email` becomes a no-op that logs
  `[MAIL-DISABLED] would send to X subject Y` and returns True. Test harness
  default.
- On send failure (non-disabled mode): logs `[EMAIL-SEND-FAILED]` with target
  + error, returns False — caller decides whether to retry / abort. Never
  raises to caller.
- Unit test (`testing/test_mailer.py`) covers send-success, send-failure,
  and MAIL_DISABLED paths via mocked HTTP.

### T2: Verification email — real delivery
**touches:** `app.py:register()`, `app.py:verify_email()`, new `/resend-verification` route
**acceptance:**
- `register()` calls `mailer.send_email()` after creating the user row.
  If send fails, the user row + token still persist (so they can request
  re-send) but a flash informs them.
- New `/resend-verification` route (rate-limited to 3/hour per IP via
  Flask-Limiter from Hotfix-2) that generates a fresh token + sends
  the email. **LOGGED-IN ONLY** — no email parameter (Inquisitor C1).
  Linked from a banner on pages that 403 with `EMAIL_NOT_VERIFIED`.
- Verification email body: subject "Verify your Window Quoting email",
  clickable link to `/verify/<token>`, 24h expiry note, plain-text fallback.
- Email template stored as Jinja2 partials in `templates/email/verify.html` +
  `templates/email/verify.txt` so future copy edits don't require code changes.

### T3: Password reset flow
**touches:** `app.py` (3 new routes), `models.py` (User columns),
  new `templates/forgot_password.html`, `templates/reset_password.html`,
  `templates/email/reset.{html,txt}`
**acceptance:**
- New columns: `password_reset_token TEXT NULL` (indexed),
  `password_reset_token_expires DATETIME NULL`. Same migration pattern
  as the verification columns.
- `/forgot-password` GET renders form; POST takes email, generates uuid hex
  token (1h expiry), emails reset link. ALWAYS returns the same flash
  regardless of whether email exists (no enumeration leak).
- `/reset-password/<token>` GET renders new-password form (uses Hotfix-2
  CSRF); POST validates token + expiry + password strength rules
  (`_password_strength_error`), sets password, clears token, logs the
  user in, redirects to `/`.
- Rate-limited: /forgot-password 3/hour/IP, /reset-password 10/hour/IP.
- Successful reset rotates `password_hash` which invalidates Flask-Login
  cookies on next request (sufficient for v1; explicit session storage
  is a Sprint 8+ candidate).

### T4: Account deletion
**touches:** `app.py` (new route), `templates/account.html`, `models.py` cascades
**acceptance:**
- `/account/delete` GET shows confirmation page with "type your email to
  confirm" + warning about subscription cancellation. CSRF token from Hotfix-2.
- POST cancels Stripe subscription via `stripe.Subscription.delete()` if
  `subscription_id` present (best-effort; logs `[STRIPE-CANCEL-FAILED]` +
  alerts admin if it errors but proceeds with deletion — the user has the
  right to leave regardless).
- **HARD DELETE** (Inquisitor C2): Cascades through quotes, profiles, transactions,
  contact_submissions via SQLAlchemy `cascade="all, delete-orphan"`.
- Deletes the per-user PDF bucket: `shutil.rmtree(_user_pdf_dir(uid))`.
- Logs `[ACCOUNT-DELETED]` audit line with user_id, email, sub_id.
- Sends a final "your account is closed" confirmation email via T1's backend.

### T5: Wire remaining transactional emails through the backend
**touches:** `app.py` (contact form, refund-failure admin notify)
**acceptance:**
- `/contact` POST sends an email to `ADMIN_EMAIL` (new env var, defaults
  to `SUPPORT_EMAIL` if unset) with the full submission, in addition to
  the existing log line.
- `[CREDIT-REFUND-FAILED]` log paths now also email `ADMIN_EMAIL` so ops
  can reconcile credits same-day.
- Every email goes through `mailer.send_email`; no direct smtplib calls
  anywhere in the codebase. Grep for `smtplib|sendgrid|mailgun|postmark`
  in app.py returns only the import in `mailer.py`.

## Out of scope

- Welcome / onboarding email sequence (Hotfix-7+ candidate)
- Email template designer / customization for end users (Hotfix-7+)
- Bounce / spam-complaint handling via webhook (Postmark surfaces these;
  monitor manually for v1)
- Two-factor auth (Sprint 8+)
- Session-storage refactor (currently cookie-only; fine for v1)

## Definition of done

- All 5 tasks pass acceptance criteria
- `testing/stress_probe.py` still passes (with WTF_CSRF_DISABLED=1 + MAIL_DISABLED=1)
- New `testing/test_mailer.py` and `testing/test_account_lifecycle.py` pass
- Manual smoke: register → receive real email → click link → /generate works
- Manual smoke: forgot password → receive real email → reset → log in works
- Manual smoke: delete account → Stripe sub cancels → user row gone → confirmation email arrives
- Commits on `hotfix-3` branch off master (post-Hotfix-2 merge)
- `notes/hotfix-3-notes.md` captures any design decisions / deferrals