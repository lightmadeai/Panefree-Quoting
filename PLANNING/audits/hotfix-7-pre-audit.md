# Hotfix-7 Pre-Audit Report

**Project:** Window Quoting (Panefree)  
**Sprint:** Hotfix-7 — Launch Execution + Deferred Polish  
**Auditor:** The Inquisitor  
**Date:** 2026-05-14  
**Verdict:** ⛔ **PRE-AUDIT — SPRINT NOT STARTED**

---

## Scope

Hotfix-7 covers the DNS flip, brand rename, email-verified gate on `/checkout`, Tailwind CDN→compiled CSS migration, UptimeRobot monitors, Stripe webhook regression tests, and a `LAUNCH.md` runbook. This is the launch sprint. Inquisitor condition **C3** (carried verbatim from H6) mandates: **no DNS flip without a PASS verdict on the full H7 sprint.**

## Sprint Status

| Field | Value |
|-------|-------|
| Proposal status | `proposed` |
| Adopted by | `pending` (Jade has NOT adopted) |
| Audit status | `pre-audit-pending` |
| Code commits for H7 | **ZERO** — latest commit is `1a1ed2b` (H6 close-out) |
| Uncommitted changes | 3 files: `PLANNING/README.md` (staged), `legal/cookie-policy.html` (modified), `legal/privacy-policy.html` (modified) |
| Untracked files | 3 audit reports (H6 post-audit, cookie policy v1/v2) |

**Finding:** Hotfix-7 has **no implementation work done**. The proposal exists but hasn't been adopted. No commits, no new files, no code changes for any of the 8 tasks (T1–T8). The only delta since H6 close-out is the uncommitted legal file edits (cookie policy rewrite from H6, PP link fix from H6).

---

## Task-by-Task Audit

### T1: LAUNCH.md — go/no-go + incident table + rollback plan
**Status:** ❌ NOT STARTED  
**Evidence:** `LAUNCH.md` does not exist at repo root. `Get-ChildItem` returns empty.

**Acceptance gaps:**
- No go/no-go checklist
- No incident response table
- No rollback plan
- No `v1.0.0` tag procedure documented
- No C3 satisfaction proof documented

**Verdict:** BLOCKING — DNS flip cannot proceed without LAUNCH.md.

---

### T2: DNS flip — Cloudflare → Render custom domain
**Status:** ❌ NOT STARTED (ops task, expected)  
**Evidence:** `config.APP_BASE_URL` still defaults to `"https://panefreequoting.com"` (line 48) — but this is the H6-era default. The `APP_BASE_URL` Render env var would need updating post-flip. No evidence of DNS configuration in code (expected — this is external ops).

**Prerequisite blockers:**
- LAUNCH.md (T1) not written — go/no-go checklist can't be run
- C3 not satisfied — this audit hasn't issued PASS
- Postmark approval not confirmed
- Cookie Policy not republished via Termly (still has H6 R4: `__cfduid` deprecated)
- Privacy Policy still has blank appeals email (`__________`) and truncated `/contac` (2 instances)

**Verdict:** BLOCKING — prerequisites not met.

---

### T3: Brand rename — "Panefree Quotes" → "Panefree Quoting"
**Status:** ❌ NOT STARTED  
**Evidence:** `git grep -F "Panefree Quotes"` returns **38 matches** across code + templates:
- **14 template files** (titles, nav, body copy): `404.html`, `500.html`, `account.html`, `account_delete.html`, `contact.html`, `forgot_password.html`, `history.html`, `index.html`, `login.html`, `profiles.html`, `profile_new.html`, `register.html`, `reset_password.html`, `top_up.html`
- **6 email template files** (subjects + body): `verify.html/txt`, `reset.html/txt`, `account_closed.html/txt`, `admin_alert.html`
- **3 app.py lines**: subjects at lines 975, 1204, 2737
- **2 mailer.py lines**: `EMAIL_FROM_NAME` default (line 88) and docstring (line 24)
- **2 config.py lines**: `EMAIL_FROM_NAME` default and comment (lines 113, 125)
- **1 test file**: `test_mailer.py` lines 123, 150
- **1 DEPLOYMENT.md line**: friendly name reference
- **Various planning/audit docs** (acceptable per acceptance: "CHANGELOG / historical-record entries")

**Acceptance criteria:** `git grep -F "Panefree Quotes"` returns ONLY changelog/historical entries. Currently returns **~30 active-code matches**.

**Verdict:** BLOCKING — zero files renamed.

---

### T4: Email-verified gate on `/checkout`
**Status:** ❌ NOT STARTED  
**Evidence:** The `/checkout` route at `app.py:2109-2180` has **NO `email_verified` check**. The route proceeds directly to `stripe.checkout.Session.create()` without any verification gate. Compare to `/generate` at `app.py:1496`:

```python
if not user.email_verified:
    return jsonify({
        "status": "error",
        "code": "EMAIL_NOT_VERIFIED",
        "message": "Verify your email address before generating quotes. ...",
    }), 403
```

The `/checkout` route is guarded only by `@login_required` and `@limiter.limit("10 per minute")`. An unverified user can create Stripe Checkout sessions, resulting in orphan sessions in the Stripe Dashboard and potential abuse (stolen-card purchases without verified email).

**Note:** The `/checkout` route is a `POST` returning `redirect(session.url, code=303)` (not JSON), so the gate should use `flash()` + `redirect(url_for("account"))` per the proposal acceptance criteria, not the JSON 403 pattern used by `/generate`.

**Verdict:** BLOCKING — security gap. Unverified users can purchase credits and subscriptions.

---

### T5: Tailwind CDN → compiled CSS
**Status:** ❌ NOT STARTED  
**Evidence:**
- **15 template files** still load `https://cdn.tailwindcss.com` via `<script>` tag
- CSP `script-src` still includes `cdn.tailwindcss.com` (line 300)
- No `tailwind.config.js` exists
- No `package.json` exists
- No compiled `static/css/tailwind.css` exists
- No Render build command for Tailwind compilation

**Security impact:** The Tailwind CDN script is a JIT compiler that executes arbitrary JavaScript in the browser. Removing it from `script-src` tightens CSP significantly (removes one external domain from script allowlist).

**Verdict:** BLOCKING per acceptance criteria — but could be deferred post-launch if T1/T2/T3/T4 are prioritized. The CSP relaxation from CDN Tailwind is a known, documented risk (H2 T4 added it to `script-src` explicitly).

---

### T6: UptimeRobot monitors
**Status:** ⚠️ PARTIALLY READY  
**Evidence:**
- `/health` endpoint exists and works (H4 T2)
- `DEPLOYMENT.md §10.1` documents UptimeRobot setup
- `BACKUP_HEARTBEAT_URL` env var referenced in `DEPLOYMENT.md §10.5` and backup scripts
- **BUT:** No UptimeRobot monitor has been configured for `panefreequoting.com` (domain doesn't resolve yet — T2 not done)
- No heartbeat URL monitor configured

**Verdict:** NON-BLOCKING — can only be completed after T2 (DNS flip). Documented setup procedure exists.

---

### T7: Stripe webhook regression test
**Status:** ❌ NOT STARTED  
**Evidence:** `testing/test_stripe_webhook.py` does not exist. No test file covers `StripeObject` vs `dict` handling — the exact bug class from H6 (Additions 4+5).

**Existing test coverage:**
- `testing/test_health.py` — health endpoint
- `testing/test_mailer.py` — email sending
- `testing/test_sentry_hooks.py` — Sentry integration
- `testing/test_retention.py` — backup retention policy
- No webhook handler test at all

**Verdict:** BLOCKING — H6 R1 explicitly called this out. The `StripeObject.get()` bug class must have regression coverage before launch.

---

### T8: Post-launch 30-min active watch + v1.0.0 tag
**Status:** ❌ NOT STARTED (ops task, expected)  
**Evidence:** No `v1.0.0` tag exists. No `notes/hotfix-7-notes.md` exists.

**Verdict:** NON-BLOCKING — can only be completed after T2 (DNS flip).

---

## Carry-Forward Heresies from H6

| ID | Description | H6 Severity | H7 Status |
|----|-------------|-------------|-----------|
| R1 | Uncommitted legal files (`cookie-policy.html`, `privacy-policy.html`) | Non-blocking | **STILL PRESENT** — files modified but uncommitted. Must commit+push before DNS flip. |
| R2 | Blank appeals email `__________` in Privacy Policy | Non-blocking | **STILL PRESENT** — 10 underscores placeholder. Must fill with `support@panefreequoting.com`. |
| R3 | Truncated `/contac` URL (2 instances in PP) | Non-blocking | **STILL PRESENT** — `panefreequoting.com/contac` missing final `t`. Must fix to `/contact`. |
| R4 | `__cfduid` cookie entry in Cookie Policy is deprecated | Non-blocking | **STILL PRESENT** — Cloudflare replaced with `__cf_bm` in May 2024. Should update. |
| R5 | `gunicorn.conf.py` docstring says "2 workers" but default is 1 | Non-blocking | **STILL PRESENT** — line 5 comment vs line 17 code disagree. |

---

## Blocking Heresies (Must Fix Before DNS Flip)

### H01: LAUNCH.md not written (T1)
The launch runbook does not exist. C3 mandates a go/no-go checklist must be executed before DNS flip. No runbook = no launch.

### H02: Email-verified gate missing on `/checkout` (T4)
**Security-critical.** Unverified users can create Stripe Checkout sessions. This is the same gate pattern as `/generate` (line 1496) but missing from `/checkout` (line 2109). The proposal acceptance criteria correctly specify: "if `not user.email_verified`, redirect to `/account` with flash message." Implementation required before ANY customer can purchase — an unverified user with a stolen card can buy credits without ever confirming their email.

### H03: Brand rename not started (T3)
38 instances of "Panefree Quotes" across 30+ files. The domain is `panefreequoting.com`. Launching with mismatched branding is a consistency failure.

### H04: Stripe webhook regression test missing (T7)
H6 Addition 4+5 fixed a `StripeObject.get()` crash class. No regression test exists to prevent recurrence. `testing/test_stripe_webhook.py` does not exist.

### H05: Uncommitted legal files (H6 R1 carry-forward)
`legal/cookie-policy.html` and `legal/privacy-policy.html` are modified but not committed. Render won't deploy these changes. Must `git add && git commit && git push` before DNS flip.

### H06: Privacy Policy blank appeals email (H6 R2 carry-forward)
`legal/privacy-policy.html` contains `__________` (10 underscores) as a placeholder for the appeals email. Must be replaced with `support@panefreequoting.com` before launch. This is a legal document with a blank field visible to users.

### H07: Privacy Policy truncated URL (H6 R3 carry-forward)
`legal/privacy-policy.html` contains 2 instances of `panefreequoting.com/contac` (missing final `t`). Broken link on a production legal page.

---

## Non-Blocking Remarks

**R1: Tailwind CDN migration is safe to defer.** T5 (compiled CSS) tightens CSP by removing `cdn.tailwindcss.com` from `script-src`, which is a genuine security improvement. However, the CDN script has been in production since H2 with no incidents. If T1–T4 and T7 are implemented and verified, T5 can ship in a follow-up sprint without blocking launch. **Recommendation:** Mark T5 as "post-launch sprint" if it blocks the launch timeline.

**R2: `gunicorn.conf.py` docstring still says "2 workers" (H6 R5).** Line 5: "Start with 2 workers" vs line 17: `workers = int(os.environ.get("GUNICORN_WORKERS", "1"))`. Code is correct per T3 decision (single-worker for v1). The docstring is misleading.

**R3: Cookie Policy `__cfduid` entry is deprecated (H6 R4).** Cloudflare replaced `__cfduid` with `__cf_bm` in May 2024. The cookie table lists `__cfduid` with a 1-year duration, which is factually incorrect. Low risk — `__cfduid` is no longer set, so users won't see it — but the legal document claims a cookie that doesn't exist.

**R4: H7 proposal adoption still pending.** `current-sprint.md` shows `adopted_by: pending`. Jade needs to formally adopt before implementation begins. This is a process concern, not a code issue.

**R5: Tailwind CDN script loads on 15 templates.** All 15 HTML templates in `templates/` load `<script src="https://cdn.tailwindcss.com">` (or reference it). If T5 is deferred, document the CSP risk acceptance in `LAUNCH.md`.

---

## Prerequisite Checklist (from H7 proposal)

| Prerequisite | Status |
|---|---|
| Postmark approval received | ⚠️ UNKNOWN — questionnaire sent 2026-05-13 ~3PM CDT; SLA 1-2 days |
| Cookie Policy revision approved + republished | ⚠️ H6 audit approved, but `cookie-policy.html` is uncommitted and still contains deprecated `__cfduid` (R3). Republish via Termly needed. |
| Privacy Policy + ToS updates per Inquisitor | ⚠️ PP has blank email (H06) and truncated URL (H07). No PP/ToS updates republished. |
| Cloudflare DNS access confirmed | ⚠️ Not verified in this audit — Chris must confirm |
| Stripe webhook re-pointing plan | ⚠️ Current webhook points at `panefree-quoting.onrender.com`. Re-pointing to `panefreequoting.com` requires DNS flip first. `whsec_…` stays valid. |

---

## Verdict

⛔ **PRE-AUDIT — SPRINT NOT STARTED**

Hotfix-7 has zero implementation commits. All 8 tasks (T1–T8) remain unstarted. The proposal hasn't been adopted. **No PASS verdict can be issued at this time.**

**7 blocking heresies** must be resolved before DNS flip:
- H01: Write LAUNCH.md (T1)
- H02: Add `email_verified` gate on `/checkout` (T4)
- H03: Brand rename "Panefree Quotes" → "Panefree Quoting" (T3)
- H04: Write Stripe webhook regression test (T7)
- H05: Commit+push legal files (H6 R1)
- H06: Fill blank appeals email in PP (H6 R2)
- H07: Fix truncated `/contac` URL in PP (H6 R3)

**Recommendation:** Prioritize H02 (security gap) and H05–H07 (legal blockers) for immediate action. H03 (brand rename) is a find/replace sweep. H01 (LAUNCH.md) and H04 (regression test) can be done in parallel. T5 (Tailwind) and T6/T8 (ops) can be phased.

**C3 REMAINS IN EFFECT:** No DNS flip until Inquisitor issues PASS on the full H7 sprint.