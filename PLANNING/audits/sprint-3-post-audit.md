---
sprint: 3
project: window-quoting
audit_type: post-audit
audited_by: Inquisitor
created: 2026-05-05
---

# Sprint 3 Post-Audit — Abuse Prevention + Free Tier Expansion + Account Security

**Verdict: PASS** ✅

All 5 tasks verified against shipped code. No drift from manifest. 3 non-blocking remarks.

---

## Task-by-Task Verification

### T1: Rate Limiting — 10 Quotes/Hour Per Account ✅

| Acceptance Criterion | Status | Evidence |
|---------------------|--------|----------|
| Each user limited to 10 quotes per rolling 60-min window | ✅ | `app.py:793-805`: `Quote.query.filter(Quote.created_at >= window_start).count()` with `RATE_LIMIT_QUOTES_PER_HOUR` (default 10) |
| Rate limit tracked via Quote.created_at timestamps | ✅ | Uses existing `Quote.created_at` index — no new table |
| Limit reached → "Next available in {X} minutes" | ✅ | `notices.build_rate_limit_notice()` computes countdown from oldest quote in window; 429 response |
| Subscriber bypass works | ✅ | Rate limit gate is inside `if not is_subscriber:` block — active subscribers skip entirely |
| past_due subscribers ARE rate-limited | ✅ | Intentional decision (documented in notes). `is_subscriber` requires `status == "active"` — past_due falls through |
| Unit test: 11th free request → 429; subscriber → success | ✅ | `TestRateLimitIntegration`: `test_free_user_eleventh_request_returns_429`, `test_subscriber_bypasses_rate_limit`, `test_past_due_subscriber_is_rate_limited` |

**Pre-audit R2 resolved:** Rolling window uses `datetime.utcnow() - timedelta(hours=1)` with indexed `created_at`. ✅

### T2: Free Tier Expansion — 10 Credits on Signup ✅

| Acceptance Criterion | Status | Evidence |
|---------------------|--------|----------|
| STARTING_CREDITS changed from 5 to 10 | ✅ | `config.py:14`: `STARTING_CREDITS = 10` |
| New user gets 10 free credits | ✅ | `app.py:register()` — `User(credit_balance=config.STARTING_CREDITS)` |
| User model default matches | ✅ | `models.py:13`: `credit_balance = db.Column(db.Integer, nullable=False, default=10)` |
| Existing users <10 get one-time top-up | ✅ | `_ensure_starting_credit_floor()` at boot: `UPDATE users SET credit_balance = :n WHERE credit_balance < :n` |
| After 10 quotes → "Buy Credits" prompt | ✅ | `NO_CREDITS` response: "Buy more (from $8.99) or subscribe to Annual Unlimited" |
| Unit test | ✅ | `TestFreeTierExpansion`: 4 tests covering constant, new user, floor migration, and no-lower-guard |

**Pre-audit note on `default=5`:** Now `default=10`. ✅ Fixed.

### T3: Custom Cap Intake Flow ✅

| Acceptance Criterion | Status | Evidence |
|---------------------|--------|----------|
| /contact page (not just mailto) | ✅ | `@app.route("/contact", methods=["GET", "POST"])` — renders `contact.html` |
| Form: company name, volume, growth, email | ✅ | All four fields captured, validated, persisted |
| Persisted to ContactSubmission model | ✅ | `ContactSubmission` model with all fields + `created_at` |
| Admin notification via console log | ✅ | `app.logger.info("[CONTACT-SUBMISSION]...")` — structured log |
| Unit test: validates, persists, success | ✅ | `TestContactIntake`: 6 tests (form render, missing fields, invalid email, valid submit, unauth redirect, soft-cap CTA wiring) |
| Soft-cap CTA wired to /contact | ✅ | `build_soft_cap_notice()` now takes `contact_url`; `/generate` passes `url_for("contact")` |

**Note:** `/contact` requires `@login_required`. Design decision documented in notes — acceptable (soft-cap CTA fires only for logged-in subscribers). ✅

### T4: Account Security Basics ✅

| Acceptance Criterion | Status | Evidence |
|---------------------|--------|----------|
| Password: ≥8 chars + ≥1 digit | ✅ | `_password_strength_error()` helper; enforced in `/register` |
| Login lockout: 5 fails → 15-min cooldown | ✅ | `LOGIN_LOCKOUT_THRESHOLD = 5`, `LOGIN_LOCKOUT_MINUTES = 15`. Counter consumed → `locked_until` set → counter reset to 0 |
| `failed_login_attempts` + `locked_until` columns | ✅ | Both on User model, both in `_ensure_table_columns` migration |
| Email verification required before /generate | ✅ | Gate checks `user.email_verified` before rate limit/reserve; returns 403 `EMAIL_NOT_VERIFIED` |
| Subscribers must also verify | ✅ | No exemption — gate fires before subscriber check. Test `test_subscriber_also_must_verify` enforces |
| Verification token: 24h expiry | ✅ | `email_verification_token_expires = datetime.utcnow() + timedelta(hours=24)` |
| `/verify/<token>` route | ✅ | One-use: clears token, flips `email_verified=True`. Re-clicks fail. Expired tokens rejected. |
| Session timeout: 24h | ✅ | `PERMANENT_SESSION_LIFETIME = timedelta(hours=24)`; sessions marked `permanent = True` |
| Pre-Sprint-3 users grandfathered | ✅ | `_backfill_email_verified()` identifies by `email_verification_token IS NULL` |
| Unit tests | ✅ | `TestPasswordStrengthHelper`, `TestRegistrationPasswordRules`, `TestLoginLockout`, `TestEmailVerificationGate`, `TestEmailVerifiedBackfill` — 13 tests total |

**Pre-audit R1 resolved:** Email delivery uses console log (`app.logger.info("[EMAIL-VERIFICATION]...")`). No `MAIL_FROM`/`SMTP_HOST` env vars added — acceptable per scope ("no email backend yet"). ✅

**Lockout counter design:** On 5th failure, counter resets to 0 and `locked_until` is set. This is correct — prevents permanent lockout after cooldown expires (documented in notes). ✅

**Unknown-email defense:** Both "wrong password" and "no such user" return generic "Invalid email or password." ✅

### T5: Documentation + Sprint 1-3 Changelog ✅

| Acceptance Criterion | Status | Evidence |
|---------------------|--------|----------|
| CLAUDE.md updated with all Sprint 3 features | ✅ | Sections for rate limiting, free tier, contact form, email verification, lockout, session timeout, new columns |
| CHANGELOG.md updated | ✅ | Sprint 3 entry with Added/Changed/Migration notes |
| RATE_LIMIT_QUOTES_PER_HOUR documented | ✅ | Documented in CLAUDE.md and CHANGELOG.md |
| New columns documented | ✅ | CLAUDE.md table includes `failed_login_attempts`, `locked_until`, `email_verified`, `email_verification_token`, `email_verification_token_expires` |

---

## Pre-Audit Remarks Tracking

| Remark | Severity | Resolution |
|--------|----------|-----------|
| R1: Email verification SMTP dependency | 🟡 | Console log fallback. No SMTP env vars added — acceptable per scope deferral. |
| R2: Rate limit rolling window | 🟢 | Implemented with indexed `created_at` query. ✅ |
| R3: ContactSubmission needs `status` column | 🟢 | **Not added.** Pre-audit suggested it; manifest didn't require it. Minor — not drift. |

---

## Non-Blocking Remarks

### 🟢 NB1: ContactSubmission lacks `status` column
Pre-audit R3 suggested adding a `status` column (default "new"). Not in manifest's acceptance criteria, so this isn't drift — but it would be useful for tracking which submissions have been followed up on. Consider adding in a future sprint.

### 🟢 NB2: T4 task weight — consider splitting for future sprints
Execution notes flag T4 as roughly equal to T1+T2 combined (5 model columns + 4 route changes + 1 new route + 13 tests). Future sprints with similar shape should split into 2-3 tasks for cleaner tracking and rollback granularity.

### 🟢 NB3: Email verification token has no resend flow
If a user's token expires, there's no UI to request a new one. Current path: "Sign in to request a new one" but no actual route exists. Not blocking — feature is functional, this is a UX gap for a future sprint.

---

## Decision Quality

The execution notes document 8 explicit decisions/deferrals, all well-reasoned:
- past_due rate limiting: correct (dunning ≠ unlimited)
- Lockout counter reset on 5th failure: prevents permanent lockout
- Subscribers must verify: closes stolen-card abuse vector
- `/contact` requires login: aligned with CTA audience
- Admin notification via `app.logger.info()`: cleaner than `print()`
- Floor migration uses `WHERE balance < N`: acceptable pre-launch
- Unknown-email generic response: standard credential-stuffing defense
- Test helper auto-verify: pragmatic, doesn't weaken verification tests

All decisions are defensible and documented. No improvisation of scope.

---

## Test Coverage Summary

| Test Suite | Tests | Status |
|-----------|-------|--------|
| `test_sprint3_pipeline.py` | ~24 tests (unittest) | ✅ All pass |
| `test_sprint3.py` | 7 tests (pytest, legacy) | ✅ All pass |
| `test_sprint2.py` | ~25 tests (unittest) | ✅ All pass |
| **Total** | **~56 tests** | **All green** |

---

## Verdict

**PASS** ✅

All 5 tasks implemented per manifest. No drift. Pre-audit remarks addressed (R1 console fallback, R2 rolling window, R3 minor omission not in spec). 3 non-blocking remarks for future consideration. Execution decisions are well-documented and defensible. Sprint 3 is cleared for merge.