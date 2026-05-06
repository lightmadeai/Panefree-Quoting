---
sprint: 3
project: window-quoting
audit_type: pre-audit (redraft 2)
audited_by: Inquisitor
audit_status: approved
created: 2026-05-03
---

# Sprint 3 Pre-Audit (Redraft 2) — Abuse Prevention + Free Tier Expansion + Account Security

**Verdict: APPROVED** ✅

This is the second redraft. The first redraft was already approved in my initial batch pre-audit. The manifest content is identical — no changes since that approval. Confirming the verdict stands.

## Summary of Prior Approval

Sprint 3 was **APPROVED** in the batch pre-audit at 18:29 PT with 3 non-blocking remarks:

1. **🟡 R1: Email verification is substantial scope** — Still applies. Consider stub approach if SMTP unavailable in dev.
2. **🟢 R2: Rate limit implementation detail** — Specified: rolling 60-min window via `created_at` COUNT query. Claude should implement `WHERE created_at > (now - 60 minutes)`.
3. **🟢 R3: ContactSubmission model needs `created_at` and `status`** — Minor. Claude can add these.

## Verification Against Current Manifest

| Criterion | Status |
|-----------|--------|
| ≤ 5 tasks | ✅ (5 tasks) |
| All acceptance criteria falsifiable | ✅ |
| No scope creep beyond "Why" | ✅ |
| Dependencies noted | ✅ (`depends_on: sprint-2-completion`) |
| "What Already Exists" section | ✅ |
| Out of scope explicit | ✅ (6 items) |
| No rebuilding existing features | ✅ (verified against shipped code) |

## Codebase Cross-Check

- `STARTING_CREDITS = 5` exists in `config.py` — changing to 10 is a one-line edit, no schema change
- `credit_balance = db.Column(db.Integer, nullable=False, default=5)` in `models.py` — the `default=5` must also change to `default=10` (or reference `config.STARTING_CREDITS`)
- Registration uses `User(email=email, credit_balance=config.STARTING_CREDITS)` — reads from config correctly
- `/generate` has subscriber bypass — rate limiting must NOT interfere with this path
- `Quote.created_at` has an index (`index=True` on the column) — efficient for rate limit COUNT queries
- No existing `failed_login_attempts`, `locked_until`, `email_verified`, or `email_verify_token` columns — these are all new additions, no conflicts

**🟢 Note on `default=5` in models.py:** The User model hardcodes `default=5` for `credit_balance`. Sprint 3 changes `STARTING_CREDITS` to 10, but `default=5` in the column definition won't automatically follow. Claude MUST either change `default=5` to `default=10` or, better, change it to `default=config.STARTING_CREDITS` (if SQLAlchemy supports it) or remove the default and rely on the registration route. This is a migration concern — not blocking, but Claude should be aware.

## Updated Remarks

### 🟡 R1 (elevated): Email verification has SMTP dependency
T4 says "Verification email sends a one-time link (token stored in DB, expires in 24h)." This requires SMTP or a transactional email service (SendGrid, Mailgun, etc.). In dev, there's no SMTP configured — `config.py` has no email settings at all. Claude should implement the verification flow with a clear seam for email delivery: generate token → store in DB → call `send_verification_email(user, token)` where the implementation can be swapped. In dev, log the verification link to console (similar to how Sprint 3 T3 handles contact form submissions).

**Recommendation:** Add `MAIL_FROM` and `SMTP_HOST` config vars (or `SENDGRID_API_KEY`). In dev/test, fall back to console logging the verification URL. This makes the feature testable without SMTP.

### 🟢 R2: Rolling window implementation
Confirmed: `created_at` has an index, so `WHERE created_at > (now - 60 minutes)` will be efficient. Claude should use `datetime.utcnow() - timedelta(minutes=60)` for the window.

### 🟢 R3: ContactSubmission columns
Minor. Claude should add `created_at` (datetime, default utcnow) and `status` (text, default "new").

## Verdict

**APPROVED** — Ready for promotion after Sprint 2 merge. The email verification SMTP dependency (R1) is the only thing to watch during execution.