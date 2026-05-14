# Hotfix-6 Post-Audit Report

**Project:** Window Quoting (Panefree)  
**Sprint:** Hotfix-6 — Production Cutover  
**Auditor:** The Inquisitor  
**Date:** 2026-05-13  
**Verdict:** **PASS** (0 blocking, 5 non-blocking remarks)

---

## Scope

Hotfix-6 enabled production cutover machinery. Per the close-out notes, T1–T4 landed; T5 (LAUNCH.md) + DNS flip + v1.0.0 tag rolled to Hotfix-7. Five Chris-authorized scope additions were also in scope.

## Task Verification

### T1: Production WSGI + ProxyFix + Legal Routes — ✅ PASS

| Sub-task | Status | Detail |
|----------|--------|--------|
| `gunicorn.conf.py` created | ✅ | Clean config: 1 worker (env-overridable), 30s timeout, stdout logging, `preload_app = False`. Reasonable defaults. |
| ProxyFix wired in `app.py` | ✅ | `x_for=1, x_proto=1, x_host=1, x_port=1` — correct for single trusted proxy (Render LB). Positioned after limiter init, before Talisman. |
| `gunicorn~=23.0.0` in requirements.txt | ✅ | Pinned major version, compatible spec. |
| `/legal/privacy` route | ✅ | Serves `privacy-policy.html`, 200 with `text/html; charset=utf-8`. Hardcoded filename — no path traversal risk. |
| `/legal/terms` route | ✅ | Same pattern, serves `terms-of-service.html`. |
| `/legal/cookies` route | ✅ | Same pattern, serves `cookie-policy.html`. |
| All 3 legal HTML files exist | ✅ | Confirmed: privacy-policy.html (137,904 B), terms-of-service.html (133,882 B), cookie-policy.html (9,713 B). |

### T2: Production env vars — ✅ PASS (code-verified)

`DATABASE_PATH` env var honoring confirmed in `config.py` line 7. All other env vars (Stripe keys, Postmark, etc.) are Render dashboard config — not auditable from code but pattern is correct.

### T3: Single-worker gunicorn decision — ✅ PASS

Documented rationale: multi-worker requires shared Redis for Flask-Limiter. Single-worker is acceptable for v1. `GUNICORN_WORKERS` env var available for scale-up post-launch.

### T4: Live Stripe smoke test — ✅ PASS

Per execution notes: real card, both tiers exercised, both refunded, subscription cancelled. Two bugs surfaced and fixed (Additions 4+5). Inquisitor condition C2 (real card + refund, not test cards) honored fully.

### Addition 1: GitHub repo creation — ✅ PASS (ops, not code)

### Addition 2: Render Disk for SQLite persistence — ✅ PASS

`config.py:7` correctly honors `DATABASE_PATH` env var with fallback to `project_root/sovereign.db`. This is a launch-critical fix — without it, every deploy wipes the database.

### Addition 3: CSP `form-action` fix — ✅ PASS

`"form-action": ["'self'", "checkout.stripe.com"]` — tight allowlist, only Stripe Checkout. No new risk surface.

### Addition 4: `event.get("id")` fix — ✅ PASS

Changed from `event.get("id")` to `event["id"]`. Correct — `StripeObject.__getattr__` intercepts `.get()` and raises `AttributeError`.

### Addition 5: StripeObject → dict conversion — ✅ PASS

```python
if hasattr(event_obj, "to_dict_recursive"):
    event_obj = event_obj.to_dict_recursive()
elif hasattr(event_obj, "to_dict"):
    event_obj = event_obj.to_dict()
```
Durable fix. Handles both `StripeObject` and plain `dict`. Idempotent. Downstream handlers can safely use `dict.get()`.

### Legal Blocker Fixes — ✅ PASS

| Blocker | Fix | Verified |
|---------|-----|----------|
| B1: PP "Cookie Notice" links pointed to `/legal/privacy` | Both links now point to `/legal/cookies` | ✅ Two instances confirmed: `href="https://panefreequoting.com/legal/cookies"` |
| B2: CP advertised advertising cookies | CP rewritten: "We do NOT use advertising cookies, marketing cookies, or third-party analytics cookies." Full cookie table added with 5 entries (session, csrf_token, __stripe_mid, __stripe_sid, __cfduid). "Do you serve targeted advertising?" → "No." | ✅ |

---

## Non-Blocking Remarks

**R1: Uncommitted legal file changes.** `legal/cookie-policy.html` and `legal/privacy-policy.html` show as modified but uncommitted. These MUST be committed and pushed before DNS flip. Without a commit+push, Render won't deploy the legal route fixes.

**R2: Blank appeals email in Privacy Policy.** The PP still contains `__________` (10 underscores) as a placeholder for the appeals email address. Should be filled with `support@panefreequoting.com` before DNS flip. This is a legal document with a blank field — not blocking for H6 audit (it was present pre-H6), but should be fixed before launch.

**R3: Truncated `/contac` URL in Privacy Policy.** Two instances of `panefreequoting.com/contac` (missing the final `t`). This appears to be a Termly template truncation issue. Should be corrected to `/contact` before DNS flip. Not blocking for H6 audit (pre-existing), but a broken link on a production legal page.

**R4: `__cfduid` cookie row is deprecated.** Per the cookie policy re-audit (R1 carried forward): Cloudflare replaced `__cfduid` with `__cf_bm` (30 min) and `cf_clearance` (30 days) in May 2024. The cookie table lists `__cfduid` with a 1-year duration, which is factually incorrect. Post-launch fix: replace with `__cf_bm` and optionally `cf_clearance`.

**R5: `gunicorn.conf.py` docstring says "2 workers" but default is 1.** Line 7 comment says "Start with 2 workers" but `workers = int(os.environ.get("GUNICORN_WORKERS", "1"))` defaults to 1. The comment and code disagree. The code is correct per T3 decision (single-worker for v1); the docstring is misleading. Non-blocking for H6, but should be corrected to avoid confusion.

---

## Inquisitor Pre-Audit Conditions

| Condition | Status | Detail |
|-----------|--------|--------|
| C1: Relabel as hotfix-6 under Stabilize | ✅ HONORED | Sprint is `hotfix-6`, phase `stabilize`. No new Ops phase. |
| C2: Real card + refund | ✅ HONORED | Both tiers tested, both refunded, sub cancelled. Live Stripe pipeline validated. |
| C3: Post-audit before DNS flip | ✅ TRANSFERS | Verbatim to H7. DNS flip is H7 scope. This audit does not gate DNS flip — H7's audit does. |

---

## Carry-Forward Remarks

From prior hotfixes still unresolved:
- **H3 R2:** `test_account_lifecycle.py` doesn't exist → H7 T7 (Stripe webhook regression test) partially addresses this class but is Stripe-specific.
- **H5 R1:** `[BACKUP-*]` tags not in DEPLOYMENT.md log catalog → still owed.
- **H5 R3:** Schema dumps accumulate without prune → negligible for v1.
- **H5 R4:** No app-level functional restore test → still owed.
- **H6 R1:** Test fixtures use `dict`, not real `StripeObject` → H7 T7 addresses.
- **H6 R2:** `LAUNCH.md` not written → H7 T1 addresses.

---

## Verdict

**PASS.** All in-scope tasks verified. 0 blocking findings. 5 non-blocking remarks (3 should be fixed before DNS flip: R1 uncommitted files, R2 blank appeals email, R3 truncated URL; 2 are post-launch polish: R4 deprecated cookie name, R5 misleading docstring).

C3 transfers verbatim to Hotfix-7: **no DNS flip without Inquisitor PASS on H7.**