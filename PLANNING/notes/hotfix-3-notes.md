# Hotfix-3 Execution Notes

**Branch:** `hotfix-3` (off master, post-Hotfix-2 merge)
**Executor:** Claude
**Per:** Jade-adopted draft with Inquisitor pre-audit conditions

---

## Decisions, deferrals, and things future-me should know

### T1 — Postmark mailer
- Picked `requests`-based HTTP client over `postmarker` lib to avoid a
  new dep. `requests` already in `requirements.txt` from Hotfix-1.
- `_is_mail_disabled()` reads env on every call rather than caching at
  import — lets individual pytest cases toggle via `monkeypatch.setenv`
  without restarting the process. Cost is one `os.environ.get` per send;
  negligible vs the ~200ms network call it gates.
- Postmark `MessageStream="outbound"` hardcoded. Postmark also supports
  `broadcast` stream for marketing email; if we ever add a newsletter,
  it goes on a separate stream because Postmark scores them independently
  for deliverability.
- `from_field` composes as `"Name <addr@domain.com>"` only when `EMAIL_FROM_NAME`
  is non-empty. Tested both paths.

### T2 — Verification email
- Kept the `[EMAIL-VERIFICATION]` log line with the verify URL. It's
  a fallback for ops debugging if a customer reports the email never
  arrived — Postmark dashboard is canonical, but the log gives offline
  forensics. Minor info-disclosure to anyone with log access; deemed
  acceptable for v1 because gunicorn logs aren't world-readable on
  managed hosts.
- `register()` persists the user row even when send fails. Transient
  email outage shouldn't lose the account; user clicks the resend banner.
- `_issue_verification_token` rotates the token each call — supersedes
  the previous one. Cleaner than tracking last-issued timestamps.
- `/resend-verification` is POST-only + `@login_required` + 3/hour/IP
  per Inquisitor C1. Enumeration vector closed.
- Banner in `_nav.html` is the discoverable UX — shows on every
  authenticated page when `email_verified=False`.

### T3 — Password reset
- Two new User columns (`password_reset_token`, `password_reset_token_expires`).
  Mirror the verification token columns. Separate columns because verify
  proves "you own this email at signup" and reset proves "you can read
  this inbox NOW" — different security domains, shouldn't accidentally
  cross.
- 1-hour expiry vs 24h for verify. Reset is higher-value; tighter window
  limits blast radius if email is forwarded.
- `/forgot-password` POST is intentionally enumeration-safe:
  - Identical flash for known vs unknown email
  - Identical 302 response
  - Zero DB writes for unknown email (no timing delta from a write)
  - 3/hour/IP rate limit to slow enumeration probes
- `/reset-password/<token>` returns 404 (not 400) for unknown OR expired
  tokens — same response, no signal about which case.
- Successful reset rotates `password_hash` (invalidates existing Flask-Login
  cookies on next request) AND clears `failed_login_attempts` + `locked_until`
  (mailbox control proves identity at least as well as a successful login).

### T4 — Account deletion (Inquisitor C2: hard delete)
- Order of operations was the careful part:
  1. Validate confirm_email
  2. Best-effort Stripe cancel (non-blocking on failure — user has legal
     right to leave regardless of Stripe API state)
  3. `logout_user()` BEFORE `db.session.delete(user)` — otherwise
     Flask-Login's before_request hook tries to load a deleted row and 500s
  4. Snapshot email + sub_id BEFORE the row goes
  5. Cascade delete via SQLAlchemy relationships
  6. `shutil.rmtree` per-user PDF bucket (non-fatal — bucket is cache)
  7. Send confirmation email
  8. `[ACCOUNT-DELETED]` audit log with snapshot
- Cascade configured in `models.py`: profiles + transactions + quotes +
  contact_submissions all `cascade="all, delete-orphan"`. Verified via
  smoke test that all 4 orphan-row queries return 0 post-delete.
- Confirmation email goes to the soon-to-be-deleted address. The user
  can't reach support via the deleted account but can still receive
  the inbox-side confirmation.

### T5 — Admin alerts
- New `_notify_admin(alert_tag, subject_summary, body_markdown)` helper
  shares one template (`templates/email/admin_alert.{html,txt}`) across
  three call sites.
- Three sites wired:
  - `/contact` POST → operator sees inquiry same-day
  - `[CREDIT-REFUND-FAILED]` → operator sees reconcile-needed alert
  - `[STRIPE-CANCEL-FAILED]` → operator sees Dashboard-cancel action item
- Best-effort by design: a failed admin email send must not cascade
  and break the primary flow it's annotating. Mailer's own
  `[EMAIL-SEND-FAILED]` log catches the failure for forensics.

---

## What Chris needs to do at H3-merge time

When this branch merges, the prod env needs these new variables (already
in `.env.example`):

| Var | Source | Notes |
|---|---|---|
| `POSTMARK_SERVER_TOKEN` | Postmark Dashboard → Server Tokens | Per-server, can be rotated |
| `EMAIL_FROM` | Postmark verified sender | Must match a verified Sender Signature OR a verified domain |
| `EMAIL_FROM_NAME` | choose | "Window Quoting" works |
| `ADMIN_EMAIL` | choose | Defaults to `SUPPORT_EMAIL` if unset — fine for solo ops |

For local dev, `testing/stress/run_server.py` auto-sets `MAIL_DISABLED=1`
so the test harness keeps working without any of the above.

Chris will get a PowerShell walkthrough when it's prod-env time
(currently parked behind H4 and H5).

---

## Open items deliberately deferred

- Real Postmark live smoke ("register → receive real email → click →
  /generate works"). Chris executes this himself after he plugs
  POSTMARK_SERVER_TOKEN into prod env — option (b) from execution plan.
- Bounce / spam-complaint webhook handling. Postmark surfaces these in
  the dashboard; monitor manually for v1.
- Welcome / onboarding email sequence. Hotfix-7+ candidate.
- Two-factor auth. Sprint 8+.
- Server-side session storage (instead of relying on `password_hash`
  rotation to invalidate cookies). Sprint 8+.

---

## Inquisitor conditions — all resolved

- **C1** (`/resend-verification` logged-in-only) — implemented as
  `@login_required` route, no email param accepted, 3/hour/IP.
- **C2** (account hard delete with audit log) — `db.session.delete(user)`
  with cascade through 4 tables + PDF dir cleanup. `[ACCOUNT-DELETED]`
  audit line with snapshot data.
- **C3** (Postmark for v1) — implemented as the only mailer backend.
  No SendGrid/SES/Mailgun code paths exist.

---

## Verification summary

| Check | Result |
|---|---|
| `testing/test_mailer.py` | 9/9 pass |
| `testing/stress_probe.py` (P1, P5, P6, P8, P9/P10, P11, P12, P13, P14, P15, P16) | All PASS or expected status |
| Locust 30u × 45s | 2415 reqs, 0 failures, p50 13ms / p95 45ms / p99 190ms |
| `grep smtplib\|sendgrid\|mailgun app.py` | 0 matches (all via mailer.py) |
| Manual: register → verify → /generate (MAIL_DISABLED path) | DB confirms token issued + 24h expiry |
| Manual: forgot → reset → login with new pw → old pw rejected → token 404 on reuse | All correct |
| Manual: account delete with wrong confirm → rejected; correct confirm → cascade clean | All correct |
| App boots cleanly with no POSTMARK_SERVER_TOKEN in DEV_MODE | Yes, with ERROR log line |
