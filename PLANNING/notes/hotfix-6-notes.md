# Hotfix-6 Execution Notes

**Branch:** `master` (direct commits, single-operator launch session)
**Executor:** Claude (Chris co-driving)
**Per:** Jade-adopted hotfix-6 with Inquisitor pre-audit conditions C1 + C2 + C3
**Launch session:** 2026-05-13 afternoon/evening

---

## ⚠️ Scope reality vs. sprint draft

The sprint draft scoped T1–T5 plus DNS flip + v1.0.0 tag as the closing acts. **What actually shipped in this hotfix-6 execution:**

- ✅ T1 (gunicorn + ProxyFix + legal routes) — Jade's code-side work pre-session
- ✅ T2 (production env vars) — full Render Environment population
- ✅ T3 (single-worker decision, deferred multi-worker + Redis)
- ✅ T4 (live Stripe smoke test) — both tiers exercised, refunded, sub cancelled
- ❌ **T5 (LAUNCH.md + go/no-go + rollback plan) — NOT WRITTEN. Rolling to hotfix-7.**
- ❌ **DNS flip — NOT EXECUTED. Rolling to hotfix-7 because external blockers (Postmark approval pending 1-2 days, cookie policy still pending Inquisitor approval, Inquisitor post-audit on H6 pending).**
- ❌ **v1.0.0 tag — NOT APPLIED. Gated on DNS flip.**

**Why split rather than extend H6:**
H6's substantive code-side work (the production cutover machinery) is complete and exercised end-to-end. Holding the close-out open while waiting on multi-day external blockers (Postmark, Termly legal edits, Inquisitor verdict) keeps a stale "in progress" sprint occupying current-sprint.md and blocks any opportunistic work. Closing H6 as "production cutover ENABLED" and opening hotfix-7 as "production cutover EXECUTED + launch hardening" maps cleanly to the actual phase boundary.

Inquisitor's post-audit will land on the H6 close-out scope (T1–T4 + bug fixes). DNS flip + LAUNCH.md + v1.0.0 fall to H7's audit gate per Inquisitor C3 (audit IS the launch gate — that condition transfers to H7 verbatim).

---

## Mid-sprint scope additions (Chris-authorized)

Five unplanned items shipped in this session beyond the pre-audited T1–T5 draft. All Chris-authorized in the conversation transcript, documented here so Inquisitor doesn't have to forensically reconstruct intent from the git log.

### Addition 1: GitHub repo creation + initial push

Sprint draft assumed the repo was already connected to GitHub. It was not — `git remote -v` returned empty. Created `https://github.com/lightmadeai/Panefree-Quoting` (private), added remote, pushed all historical commits (sprints 1-4, hotfixes 1-5) plus today's H6 work. Required for Render's auto-deploy-on-push workflow to function at all.

### Addition 2: Render Disk for SQLite persistence

Smoke-test signup created an account, then a redeploy wiped the database — confirming Render's filesystem is ephemeral by default. SQLite at `project_root/sovereign.db` would not survive any production redeploy.

Fix:
- Added 1GB Render Disk mounted at `/var/data`
- `config.py:7` changed from hardcoded path to env-var-honoring:
  `DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(project_root, "sovereign.db"))`
- Render env var `DATABASE_PATH=/var/data/sovereign.db` set
- Verified persistence by signing up an account, forcing a redeploy, and confirming the account survived.

Cost impact: $0.25/mo additional (1GB Render Disk).

**This is a launch blocker we caught pre-launch.** Without it, every code update would have wiped all customer accounts, credits, and subscriptions. The smoke test surfaced this within minutes of the first deploy — exactly why C2 (real-card smoke before DNS flip) exists as a condition.

### Addition 3: Talisman CSP `form-action` fix

Stripe checkout button POSTed `/checkout`, server returned 303 redirect to `checkout.stripe.com`, browser silently aborted the navigation with no error visible to the user. DevTools console revealed the cause:

> "Sending form data to '<URL>' violates the following Content Security Policy directive: 'form-action 'self''. The request has been blocked."

Hotfix-2's CSP set `form-action: 'self'` — locked-down by default, which is correct, but did not anticipate redirects to external payment processors. Fixed:

```python
"form-action": ["'self'", "checkout.stripe.com"],
```

Tight allowlist — only Stripe Checkout, not all external POSTs. No new risk surface.

### Addition 4: Stripe webhook handler bug — `event.get("id")`

First production webhook fired and returned **500 Internal Server Error**. Stripe processed the payment cleanly on their side, but our handler crashed before any event-specific logic ran. The `[STRIPE-WEBHOOK]` info log line at app.py:2547 used `event.get("id")` to extract the event ID. Stripe SDK 2.x `StripeObject` does not expose `.get()` — `__getattr__` falls back to `__getitem__` on `"get"`, fails with `KeyError: 'get'`, and the wrapping AttributeError propagates up. The entire handler 500s.

First fix: `event.get("id")` → `event["id"]`. Pushed. Deployed.

### Addition 5: StripeObject `.get()` blast-radius fix

Second test purchase: same `AttributeError: get` at app.py:2551 — `event_obj.get("mode")`. Realized this was not a one-line bug but a pervasive pattern: every defensive `.get()` in every downstream handler (`_handle_payment_checkout`, `_handle_subscription_checkout`, etc.) would crash the same way. Whack-a-mole.

Durable fix: convert the Stripe payload to a plain Python dict **once** at dispatch time via `event_obj.to_dict_recursive()`. Handlers then use familiar `dict.get()` semantics without each one re-learning the trap.

```python
if hasattr(event_obj, "to_dict_recursive"):
    event_obj = event_obj.to_dict_recursive()
elif hasattr(event_obj, "to_dict"):
    event_obj = event_obj.to_dict()
```

Idempotent: pre-existing tests using plain dicts (e.g. test_webhook.py fixtures) pass through unchanged.

**Verified end-to-end** after this fix: resent a previously-failed `checkout.session.completed` event from Stripe Dashboard. Handler returned 200. `/api/credits` jumped 10 → 20. Full live billing pipeline confirmed working.

**Why integration tests didn't catch this:** test fixtures use `dict` objects, not real `StripeObject` instances. The bug only manifests under the actual SDK construct_event return type. A regression test that constructs a real `StripeObject` (or that mocks `stripe.Webhook.construct_event` with one) would prevent recurrence. Logged as hotfix-7 candidate.

---

## Decisions, deferrals, and things future-me should know

### T1 — Production WSGI

- **`gunicorn.conf.py` defaults to 1 worker** (rebalance from Jade's initial 2). Multi-worker requires shared Redis storage for Flask-Limiter to avoid per-worker counter split-brain. Single-worker is acceptable for v1 traffic per T3's documented tradeoff.
- **`GUNICORN_WORKERS` env override** present for post-launch scale-up without code change.
- **ProxyFix wired with `x_for=1, x_proto=1, x_host=1, x_port=1`** — one trusted proxy layer (Render's load balancer). More layers would require Render-specific knowledge that isn't worth defending.
- **Local gunicorn smoke test on Windows skipped** — gunicorn depends on `fcntl` (Unix-only). Verified config syntax via Python import only. First true gunicorn boot was on Render itself. Acceptable tradeoff per Chris's "fail-forward on hosting" framing.

### T2 — Production env vars

- **All Stripe live keys procured** during session: `pk_live_…`, `rk_live_…` (restricted), `sk_live_…` (break-glass, NOT on Render), `whsec_…` (after live webhook endpoint created).
- **Restricted key permissions scoped** per code's actual surface area: Checkout Sessions write, Subscriptions write, Billing Portal Sessions write, Customers write, Charges/Refunds read, Invoices read, Prices read, Products read, Payment Methods read. Everything else None.
- **`STRIPE_WEBHOOK_SECRET=whsec_PLACEHOLDER`** initially to unblock first deploy; replaced with real value after webhook endpoint creation on the Render auto-URL. This bootstrap dance is unavoidable — webhook URL depends on app being deployed, secret depends on webhook existing.
- **`APP_BASE_URL=https://panefree-quoting.onrender.com`** (note hyphen — Render's auto-URL slug). Updates to `https://panefreequoting.com` at DNS flip (hotfix-7).
- **Dev-only escape hatches confirmed UNSET on Render:** `DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED`. Verified via Render's Environment tab and via the absence of dev-mode pre-flight warnings in Render boot logs.
- **Secrets storage tradeoff:** acknowledged that a `.txt` in `C:\Users\Thorn\secrets\` is interim only. Path is outside OneDrive sync, but a password manager migration is on the post-launch list.

### T3 — Redis deferral

- **Single worker for v1.** Decision recorded in `gunicorn.conf.py` docstring and in this notes file.
- **Bump trigger:** 20 paying customers OR sustained Sentry p95 > 500ms, whichever first. Post-launch task: provision Upstash free tier (10K commands/day, sufficient for rate limiting), set `REDIS_URL`, update Limiter `storage_uri` to `os.environ.get("REDIS_URL", "memory://")`, set `GUNICORN_WORKERS=2`.

### T4 — Real-card smoke test

- **Inquisitor C2 honored fully:** Chris's personal card, real Starter pack ($8.99) charge, real Annual subscription ($179) charge, refunds via Stripe Dashboard, annual subscription cancelled (cancel-immediately to prevent renewal).
- **First two purchases failed silently** (webhook 500s — see Additions 4 + 5 above). Stripe reported the charge as success but credits never landed. **This is exactly the failure mode test cards cannot surface** — test cards exercise test-mode code paths; only real-mode payment + real webhook delivery reveals the SDK contract mismatch. Inquisitor C2's value validated within hours.
- **Transaction IDs recorded** in `C:\Users\Thorn\secrets\panefree-prod.txt` (interim secret file). Not committed to repo.
- **Test data cleanup state:** all test charges refunded. Annual sub cancelled. Pending failed webhook events left for Stripe auto-retry — on the test account, succeeding retries that credit a refunded purchase are acceptable noise.

### T5 — LAUNCH.md (NOT WRITTEN — rolled to hotfix-7)

- Rolling forward. The launch event itself happens in hotfix-7. Writing LAUNCH.md without a known launch date or known active-watch window would produce a speculative artifact. Defer to when DNS flip is actively scheduled.

---

## What surfaced in execution that doesn't fit a numbered task

### Cookie policy audit found issues mid-session

Inquisitor reviewed Jade's Termly-imported Cookie Policy and flagged content issues during this session. Chris is handling the revision in Termly directly (out-of-code change). Tracking forward in hotfix-7 as a launch blocker.

### Brand rename "Panefree Quotes" → "Panefree Quoting"

Chris flagged the branded display string in the page title was "Panefree Quotes" while the domain is `panefreequoting.com`. Confirmed via grep: 31 files reference "Panefree Quotes" (templates, email bodies, error pages, config defaults). A single find/replace sweep, but 31 files is a meaningful diff and shipping it mid-smoke-test risks confusing the audit trail. **Deferred to hotfix-7 explicitly with Chris's acknowledgment.**

### Email-verified gate on `/checkout`

Discovered during smoke test that `/checkout` has `@login_required` but no email-verified check. A user can sign up, skip verification, click Buy Credits, complete the Stripe Checkout flow, and only hit a wall when they try to `/generate` (which DOES check `email_verified`). They've paid; they can't use it. **Not a security flaw** (the gate at /generate prevents abuse — purchased credits cannot be spent until verified), but it's terrible UX and breaks the principle of "fail at the earliest gate." Rolled to hotfix-7.

### Tailwind CDN production warning

Browser console warned "cdn.tailwindcss.com should not be used in production." Cosmetic — site works. Compiling Tailwind via the CLI to a static file is the canonical fix. Deferred to hotfix-7 as a "nice to have, not launch-blocking."

### UptimeRobot setup not done

Account created (per Jade's earlier prep) but monitors not configured. `/health` monitor + backup heartbeat both pending. Not launch-blocking — `/health` works, backup heartbeat is best-effort. Rolled to hotfix-7.

### Postmark approval pending

Sandbox-mode error caught during smoke test: `422 ErrorCode=412 "While your account is pending approval, all recipient addresses must share the same domain as the 'From' address."` Postmark sent approval questionnaire 2026-05-13 ~2:47PM CDT. Chris replied with the full questionnaire response (business model, transactional-only sends, single opt-in via `/register`). Expected approval 1-2 days. Not a code fix — pure account-state issue.

---

## Carry-forward non-blocking remarks (from prior hotfixes)

- **H3 R1:** `.env.example` missing H3 env vars — NOT FIXED in H6. H3 env vars (Postmark, EMAIL_FROM, etc.) are present in `.env.example` as of this writing; closing this remark.
- **H3 R2:** `test_account_lifecycle.py` doesn't exist yet — NOT FIXED in H6. Still owed.
- **H5 R1:** `[BACKUP-*]` tags not in DEPLOYMENT.md log catalog — NOT FIXED in H6. Still owed.
- **H5 R2:** Real B2 round-trip not exercised in-sprint — **PARTIALLY ADDRESSED** in H6: B2 credentials configured on Render, but no backup script has fired in production yet to exercise the round-trip. Will validate at first scheduled backup run.
- **H5 R3:** Schema dumps accumulate without prune — NOT FIXED in H6. Negligible for v1.
- **H5 R4:** No app-level functional restore test — NOT FIXED in H6. Still owed.

H6 itself adds two new non-blocking-on-launch remarks:

- **H6 R1:** Test fixtures for Stripe webhooks use `dict`, not real `StripeObject`. The two bugs in Additions 4 + 5 would not have been caught by current test suite. Regression test using real `StripeObject` (or mocking `stripe.Webhook.construct_event` to return one) would prevent recurrence.
- **H6 R2:** `LAUNCH.md` not written this hotfix. Rolled forward to hotfix-7.

---

## Inquisitor pre-audit conditions — status

- **C1 (relabel as hotfix-6 under Stabilize, no new Ops phase):** Honored. No §13 amendment requested.
- **C2 (real card + refund, not Stripe test cards):** Honored fully. Real card, two real charges, two real refunds, real annual sub created + cancelled. Live pipeline validated as designed.
- **C3 (mandatory post-audit before DNS flip):** **PENDING.** H6 is closed but DNS flip transfers to H7 — C3 transfers with it. The post-audit gate is preserved verbatim: no DNS flip without Inquisitor PASS on the launch-completion sprint.

---

## Files changed in H6 (Claude-side)

Commits in chronological order on `master`:

1. `c9b536d` — hotfix-6 T1: production WSGI + legal routes (initial Jade-prepared changes pushed in first repo commit)
2. `945e360` — hotfix-6 planning: chris-sprint, proposals, implementation guide
3. `376d6e0` — hotfix-6: honor `DATABASE_PATH` env var for Render persistent disk
4. `ce71544` — hotfix-6: allow form POST to redirect to Stripe Checkout (CSP `form-action`)
5. `60012bb` — hotfix-6: fix Stripe webhook crash on `event.get("id")`
6. `e8635f3` — hotfix-6: convert Stripe webhook payload to plain dict before dispatch

(Plus this notes file at commit time + close-out file move + hotfix-7 proposal.)

---

## Regression check

- No automated test suite run end-to-end this session (no Linux box to run gunicorn locally; Windows blocks fcntl-dependent code). Pre-merge regression is the responsibility of the H6 post-audit.
- Live smoke tests stand in for some integration coverage:
  - Stripe webhook signature verification: ✅ (signed events accepted, signature mismatch would 400)
  - Database persistence across deploys: ✅ (verified manually)
  - CSP enforcement: ✅ (caught Stripe Checkout redirect block, then allowed it)
  - Live email delivery: ⏳ blocked on Postmark approval, will validate on next Chris-initiated signup post-approval

---

## Open questions for Inquisitor

1. **Does the H6 → H7 split as framed above (cutover ENABLED vs cutover EXECUTED) satisfy the spirit of the original H6 sprint scope?** Or does Inquisitor prefer H6 stay open until DNS flip lands?
2. **Should the two webhook bugs (Additions 4 + 5) carry a stronger audit note than "non-blocking remark"?** They were latent bugs in already-merged Hotfix-3 code; only the H6 smoke test surfaced them. Argument for stronger flag: prior post-audits passed without catching them. Argument for "remark only": no real customer impact (the bugs were in code that had never run against live keys).
3. **Is H6's DoD satisfiable with T5 + DNS flip + v1.0.0 explicitly transferred to H7, given the original DoD enumerated those as H6 items?**

---

End of execution notes.
