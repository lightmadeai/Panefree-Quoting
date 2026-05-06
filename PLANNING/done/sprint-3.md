---
sprint: 3
project: window-quoting
drafted_by: Jade
redraft: true
redraft_reason: Depends on redrafted Sprint 2. Removed credit_balance/credit_tier duplication, aligned rate limit scope.
status: draft
created: 2026-05-03
redrafted: 2026-05-03
depends_on: sprint-2-completion
audit_status: approved
---

# Sprint 3 — Abuse Prevention + Free Tier Expansion + Account Security

## Why
Sprint 2 updated pricing and added the soft-cap CTA. Sprint 3 protects the business: rate limiting prevents account sharing, expanded free tier drives signups, and account security prevents abuse.

## What Already Exists (do NOT rebuild)
- `credit_balance` on User model (default=5) — this IS the free tier, just needs a higher starting value
- `STARTING_CREDITS = 5` in config — change this to expand the free tier
- Subscriber bypass on `/generate` — rate limiting must NOT break this

## Tasks

### T1: Rate Limiting — 10 Quotes/Hour Per Account
**Acceptance Criteria:**
- Each user limited to 10 quote requests per rolling 60-minute window
- Rate limit tracked via timestamps on the Quote model (no new table needed — use `created_at` with a COUNT query)
- When limit reached, user sees: "You've reached 10 quotes this hour. Next available in {X} minutes."
- Subscriber bypass still works — Unlimited subscribers are NOT subject to the rate limit (they bypass credit checks already)
- Unit test: 10 rapid quotes from a free user → 11th returns 429 with countdown; subscriber sends 11th → succeeds

### T2: Free Tier Expansion — 10 Credits on Signup
**Acceptance Criteria:**
- `STARTING_CREDITS` in `config.py` changed from 5 to 10
- New user registration grants 10 free credits
- After 10 quotes, user sees "Buy Credits" prompt with pricing comparison
- Existing users with `credit_balance < 10` get a one-time top-up migration (add migration in `_ensure_table_columns` or a startup hook)
- Free tier credits never expire
- Unit test: new user → `credit_balance=10`, 10 quotes → `credit_balance=0` → "Buy Credits" prompt

### T3: Custom Cap Intake Flow
**Acceptance Criteria:**
- Soft-cap CTA (from Sprint 2 T3) links to a dedicated `/contact` page (not just mailto)
- Contact form: Company name, current quote volume, expected growth, email
- Form submission stored in a new `ContactSubmission` model (no email backend yet — just persist to DB)
- Admin notification: logged in console for now (email delivery deferred to a later sprint)
- Unit test: form validates required fields, persists to DB, returns success message

### T4: Account Security Basics
**Acceptance Criteria:**
- Password strength enforcement on registration: min 8 chars, at least 1 number
- Login lockout: 5 failed attempts → 15-minute cooldown (track in `failed_login_attempts` and `locked_until` columns on User)
- Email verification required before first quote (new column `email_verified`, default False; `/generate` checks this)
- Verification email sends a one-time link (token stored in DB, expires in 24h)
- Session timeout after 24 hours of inactivity (Flask session config)
- Unit test: weak password rejected; 5 failed logins lock account; unverified email blocks quote generation

### T5: Documentation + Sprint 1-3 Changelog
**Acceptance Criteria:**
- Update `CLAUDE.md` with rate limiting architecture, free tier changes, contact form, and security features
- Update `CHANGELOG.md` with Sprint 3 additions
- Document rate limit configuration: `RATE_LIMIT_QUOTES_PER_HOUR` env var (default 10)
- Document new columns: `failed_login_attempts`, `locked_until`, `email_verified`

---

## Out of Scope
- Admin dashboard for user management
- Promo codes / discount codes
- Credit expiration
- Referral credits
- Email delivery backend for contact form (just persist to DB)
- A/B testing on pricing pages