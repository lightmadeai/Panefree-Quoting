---
sprint: 3
project: window-quoting
audit_type: pre-audit (redraft)
audited_by: Inquisitor
audit_status: approved
created: 2026-05-03
---

# Sprint 3 Redraft Pre-Audit — Abuse Prevention + Free Tier Expansion + Account Security

**Verdict: APPROVED** ✅ (2 non-blocking remarks, 1 conditional note)

All 4 original blockers addressed. Redraft is well-scoped and correctly references existing code. Rate limiting correctly exempts Unlimited subscribers.

## Original Blocker Resolution

| # | Original Blocker | Resolution |
|---|-----------------|------------|
| B1 | Rate limits Unlimited subscribers | ✅ Explicitly exempted. "Subscriber bypass still works — Unlimited subscribers are NOT subject to the rate limit" |
| B2 | Duplicates `STARTING_CREDITS=5` | ✅ Acknowledges existing config. T2 changes the value from 5 to 10, not adds a new column |
| B3 | Custom cap form has no backend spec | ✅ Now specifies: `/contact` page, `ContactSubmission` model, persist to DB, console log for now |
| B4 | Email verification is scope creep | ✅ Still included, but scope is now explicit with clear acceptance criteria |

## Task Review

### T1: Rate Limiting — 10 Quotes/Hour Per Account ✅
- Uses `Quote.created_at` with COUNT query — no new table, leverages existing data
- **Correctly exempts Unlimited subscribers** — they bypass credit checks already
- Falsifiable: 10 rapid quotes from free user → 429; subscriber → 200
- Uses existing `created_at` timestamps — clean implementation

### T2: Free Tier Expansion — 10 Credits on Signup ✅
- Changes `STARTING_CREDITS` from 5 to 10 — config change, no schema bloat
- One-time migration for existing users with `credit_balance < 10` — good catch
- Falsifiable: new user → balance=10, 10 quotes → balance=0
- Credits never expire — aligns with product promise

### T3: Custom Cap Intake Flow ✅
- `/contact` page (not just mailto) — addresses original blocker B3
- `ContactSubmission` model persists to DB — no email backend needed yet
- Console logging as interim notification — pragmatic
- Falsifiable: form validates, persists, returns success

### T4: Account Security Basics ✅
- Password strength: min 8 chars, 1 number — reasonable
- Login lockout: 5 failed → 15-min cooldown — specified with columns (`failed_login_attempts`, `locked_until`)
- Email verification: `email_verified` column, blocks `/generate` — acceptance criterion is clear
- Session timeout: 24h inactivity via Flask config
- Falsifiable: weak password rejected, 5 fails lock account, unverified email blocks quote

### T5: Documentation ✅
- Rate limiting architecture, free tier changes, contact form, security features
- New columns documented: `failed_login_attempts`, `locked_until`, `email_verified`
- Falsifiable: files committed

## Protocol Compliance

| Criterion | Status |
|-----------|--------|
| ≤ 5 tasks | ✅ (5 tasks) |
| All acceptance criteria falsifiable | ✅ |
| No scope creep beyond "Why" | ✅ |
| Dependencies noted | ✅ (`depends_on: sprint-2-completion`) |
| "What Already Exists" section | ✅ |
| Out of scope explicit | ✅ (6 items) |

## Non-Blocking Remarks

### 🟡 R1: Email verification is still substantial scope
T4's email verification requires: (1) a `email_verified` column and migration, (2) a verification token column or separate table, (3) a `/verify/{token}` route, (4) email sending infrastructure (SMTP config or SendGrid), (5) token expiry logic, (6) resend verification flow.

This is the heaviest task in the sprint. If Claude encounters issues with email delivery (which is likely in a dev environment without SMTP configured), it could block the entire sprint. **Recommendation:** Consider making email verification a stub — set the column and the check, but queue the email for later delivery. The acceptance criterion "unverified email blocks quote generation" can be tested with a manual token injection.

### 🟢 R2: Rate limit implementation detail
T1 says "rolling 60-minute window" using `created_at` COUNT query. This works for normal usage but has a known limitation: if a user generates 10 quotes at 10:59 and then 1 more at 11:01, they'll be rate-limited even though the first batch was "last hour." A true sliding window would count quotes from (now - 60min), which is what the acceptance criterion describes. Claude should implement the COUNT query as `WHERE created_at > (now - 60 minutes)`, not a fixed-hour bucket. This is likely what was intended — flagging for clarity.

### 🟢 R3: ContactSubmission model should have a created_at timestamp
T3 doesn't specify model columns beyond the form fields. Add `created_at` (datetime, default utcnow) and `status` (text, default "new") so submissions don't pile up with no way to triage them. Minor — Claude can add this.

## Dependency Note

Sprint 3 depends on Sprint 2 completion. The soft-cap CTA link in Sprint 2 T3 becomes the entry point for Sprint 3 T3's `/contact` page. This dependency chain is correct and well-documented.

**Verdict: APPROVED** — Ready for promotion after Sprint 2 completes. Consider stub approach for email verification if SMTP isn't available in dev.