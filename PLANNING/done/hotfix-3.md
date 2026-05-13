---
label: hotfix-3
project: window-quoting
phase: stabilize
status: done
created: 2026-05-12
completed: 2026-05-12
audit_status: pending
audit_note: "All 5 tasks landed, regression clean. Awaiting Inquisitor post-audit."
inquisitor_conditions_resolved:
  C1: "/resend-verification @login_required + @limiter.limit('3 per hour') + no email param"
  C2: "Hard delete + cascade through 4 tables + PDF dir cleanup + [ACCOUNT-DELETED] audit log"
  C3: "Postmark is the only mailer backend; no SendGrid/SES/Mailgun paths"
---

# Hotfix-3 — User Access Lifecycle (DONE)

## Outcome

5 tasks completed. The product is now usable end-to-end for new users
who couldn't satisfy the `email_verified` gate previously. All three
Inquisitor pre-audit conditions resolved.

| Task | What | Verification |
|---|---|---|
| T1 | Postmark mailer (`mailer.py`) + MAIL_DISABLED kill switch | 9/9 unit tests via mocked HTTP |
| T2 | Real verification email + `/resend-verification` (logged-in-only) + unverified banner | Smoke: register → token + expiry persisted; resend rotates token; banner renders |
| T3 | Password reset flow (2 columns, 3 routes, 2 templates, 1 email template) | Smoke: full reset cycle including 404-on-token-reuse |
| T4 | Account deletion (hard delete + Stripe cancel + audit log + confirmation email) | Smoke: wrong confirm rejected, right confirm cascades through 4 tables + PDF dir |
| T5 | Admin alerts via mailer for contact form + refund-failure + Stripe-cancel-failure | grep clean: no smtplib/sendgrid/mailgun in app.py |

## Regression evidence (no drift from Hotfix-2)

- `testing/test_mailer.py` — 9/9 PASS
- `testing/stress_probe.py` — 13/13 probes PASS or expected status
- Locust 30u × 45s — 2415 reqs, **0 failures**, p50 13ms / p95 45ms / p99 190ms
- DB sanity post-locust: stress free users at 490/500 (10 spent each),
  subs at 500/500 (bypass works), quote numbering sequential no gaps

## Commits on `hotfix-3`

```
hotfix-3 T1: Postmark email backend + MAIL_DISABLED kill switch
hotfix-3 T2: verification email real delivery + /resend-verification
hotfix-3 T3: password reset flow
hotfix-3 T4: self-serve account deletion (hard delete per Inquisitor C2)
hotfix-3 T5: wire admin alerts through mailer
```

Plus the master-side adoption commit (Jade promoting draft → current-sprint).

## What Chris needs at prod-env time

Three new env vars (Chris will get a PowerShell walkthrough when it's
deploy time, currently behind H4 and H5):

```
POSTMARK_SERVER_TOKEN  # from Postmark Dashboard → Server Tokens
EMAIL_FROM             # must be a Postmark-verified sender or domain
EMAIL_FROM_NAME        # display name; e.g. "Window Quoting"
ADMIN_EMAIL            # ops alert destination; defaults to SUPPORT_EMAIL
```

Two test-only kill switches (already in `.env.example`, must NOT be set
in prod): `MAIL_DISABLED=1` (skips real Postmark sends), plus the H2
ones (`DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`).

## Open items for Inquisitor post-audit

1. Is keeping the `[EMAIL-VERIFICATION]` log line with the verify URL
   acceptable for v1, or should we scrub the URL? (Trade-off: ops
   debug-ability vs minor info disclosure to anyone with log access.
   Defended in notes/hotfix-3-notes.md T2 section.)
2. `register()` returns 302 + flash even when verification email send
   fails. Alternative: roll back the user row. Lean was "persist + flash
   error + offer resend" because losing the account on a transient
   email outage is worse than the inconvenience of one resend click.
   Inquisitor's call.
3. Cascade behavior: `models.py` relationships use `cascade="all, delete-orphan"`
   which means orphan rows (children whose parent FK is cleared) also get
   deleted. For our schema this can't happen in practice (user_id is
   NOT NULL on all child tables), but it's worth noting that orphan-delete
   semantics aren't strictly required — just the cascade-on-parent-delete
   half. Defensible either way.

## Phase status

- Stabilize phase: still active. H4 (observability) is next; depends on
  this merge.
- Backlog: clean. No new P0/P1 items surfaced during execution.
