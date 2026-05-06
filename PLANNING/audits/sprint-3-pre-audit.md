---
sprint: 3
project: window-quoting
audit_type: pre-audit
audited_by: Inquisitor
audit_status: rejected
created: 2026-05-03
---

# Sprint 3 Pre-Audit — Abuse Prevention + Free Tier + Custom Cap

**Verdict: REJECTED** ❌

Sprint 3 depends on Sprint 2, which has been rejected. Additionally, Sprint 3 has its own heresies that must be addressed regardless of the Sprint 2 redraft.

## Blocking Heresies

### 🚫 B1: T1 rate limit contradicts Sprint 1 subscriber bypass
Sprint 1's `/generate` route has an explicit bypass for active subscribers — no credit deduction, no throttle. Sprint 3 T1 says "Admin/Unlimited users subject to same limit (prevents shared logins regardless of tier)" — a 10-quotes/hour hard cap on Unlimited subscribers directly contradicts the product promise of "unlimited quotes."

An annual subscriber paying $149/yr who hits 10 quotes/hour during a busy workday is **locked out of the product they paid for**. This is not abuse prevention — it's a broken value proposition.

**Remediation:** Rate limiting should only apply to credit-pack and free-tier users. Unlimited subscribers should have either no rate limit or a much higher threshold (e.g., 100/hour as an API-level protection, not a product-level restriction). The acceptance criterion "Admin/Unlimited users subject to same limit" must be removed.

### 🚫 B2: T2 free tier conflicts with existing `STARTING_CREDITS`
`config.py` already has `STARTING_CREDITS = 5`. The User model defaults `credit_balance` to 5. This is already implemented — new users get 5 free credits. T2 proposes "New user registration grants 5 free credits (`credit_balance=5, credit_tier=free`)" as if it's new work.

The `credit_tier=free` part is the same unnecessary schema bloat rejected in Sprint 2's pre-audit. Derive tier from state, don't store it.

**Remediation:** Remove `credit_tier` references. If free-tier limits are needed (e.g., "credits don't stack with first purchase"), specify those as business logic, not as a new enum column.

### 🚫 B3: T3 custom cap intake form — no acceptance criteria for backend
"Form submission sends to a shared inbox (or triggers a notification)" is vague to the point of non-falsifiability. Which inbox? What notification mechanism? What happens when the form is submitted? This is a "build a contact form" task with no specification of the delivery mechanism.

**Remediation:** Specify: (a) what service receives the form (email via SendGrid? Slack webhook? database row?), (b) what the user sees after submission, (c) how the notification reaches Chris/Solis. Make the acceptance criterion testable: "Form submission sends email to `scaling@windowquoting.com` via SendGrid API. Response includes success confirmation."

### 🚫 B4: T4 email verification — major scope creep for a "security basics" task
"Email verification required before first quote" is a significant feature: SMTP integration, verification token generation, token expiry, resend flow, rate limiting on the verification endpoint itself. This is not "account security basics" — it's a full email verification pipeline.

**Remediation:** Either remove email verification from this sprint (it's a standalone sprint's worth of work) or reduce it to a stub that queues the verification email but doesn't block quote generation until verified. The current acceptance criterion "required before first quote" makes it a hard blocker for new users.

## Non-Blocking Remarks

### 🟡 R1: T1 acceptance criterion is imprecise
"10 quote requests per rolling 60-minute window" — rolling by what timestamp? Quote `created_at`? A `last_quote_at` column? If the latter, you need a migration to add it, which isn't in T1's scope. Specify the implementation mechanism.

### 🟡 R2: T4 session timeout — "24 hours of inactivity" needs clarification
Flask's default session cookie doesn't have inactivity-based expiry. This requires either: (a) server-side session storage with TTL, (b) a last-activity timestamp + middleware check, or (c) a client-side mechanism. Specify which approach.

### 🟢 R3: T5 documentation — acceptable scope
Documentation task is reasonable. No issues.

## Dependency Chain

Sprint 3 is blocked by Sprint 2's redraft. Even if Sprint 3 were otherwise clean, it cannot proceed until Sprint 2 is re-approved and completed. The current Sprint 3 references Sprint 2's `credit_tier` and soft-cap CTA, both of which need to be redesigned.

**Verdict: REJECTED** — Redraft required after Sprint 2 is re-approved. Address B1-B4 before re-submitting.