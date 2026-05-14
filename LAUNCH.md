# LAUNCH.md — Panefree Quoting Production Launch Runbook

**Project:** Window Quoting (Panefree Quoting)
**Domain:** `panefreequoting.com` (registered, DNS managed in Cloudflare)
**Hosting:** Render (Starter plan, single web service, 1 GB persistent disk)
**Solo operator:** Chris Thornton (`lightmadeai@gmail.com`)
**Sprint authority:** Hotfix-7 — Launch Execution
**Audit gate:** Inquisitor C3 (carried verbatim from H6) — **no DNS flip without PASS verdict on H7**

---

## 0. Pre-Launch State (one-time read before any task in this runbook)

This runbook assumes the following are TRUE before any action below is taken:

- [ ] All H7 blocking heresies cleared in Inquisitor's pre-audit (H01-H07)
- [ ] Inquisitor has issued a **PASS** verdict on Hotfix-7 (C3 satisfied)
- [ ] Postmark account approved out of sandbox mode
- [ ] All legal docs (Privacy Policy, Terms of Service, Cookie Policy) republished via Termly, committed, deployed
- [ ] Brand rename "Panefree Quotes" → "Panefree Quoting" complete in code
- [ ] Render env var `EMAIL_FROM_NAME` updated to `Panefree Quoting`
- [ ] Stripe statement descriptor set to `Lightmade Software` (or refined per post-launch task)
- [ ] Stripe webhook regression test in CI / runnable locally and passing (`pytest testing/test_stripe_webhook.py -v` → 6/6 green)
- [ ] You have at least 60 minutes of uninterrupted attention available for the watch window

If any of the above is false, **stop** and resolve before continuing. The runbook below assumes prerequisites are met.

---

## 1. Go / No-Go Checklist

Run this immediately before the DNS flip. Every item is a hard gate; if any answer is NO, abort and fix.

### Code & deploy state

- [ ] `git log --oneline -1` shows the intended launch commit on `master`
- [ ] Render dashboard → Events tab → most recent deploy is **Live** (green)
- [ ] Render logs show recent `Listening at: http://0.0.0.0:10000` (or whatever port) with no boot errors
- [ ] Curl `https://panefree-quoting.onrender.com/health` returns `200 {"status":"ok","db":"ok",...}`
- [ ] Curl `https://panefree-quoting.onrender.com/legal/privacy` returns 200 with HTML
- [ ] Curl `https://panefree-quoting.onrender.com/legal/terms` returns 200 with HTML
- [ ] Curl `https://panefree-quoting.onrender.com/legal/cookies` returns 200 with HTML

### Env vars (sample from Render Environment tab — confirm presence, not values)

- [ ] `SRE_SECRET_KEY` set
- [ ] `APP_BASE_URL` currently set to `https://panefree-quoting.onrender.com` (will change to `panefreequoting.com` post-flip)
- [ ] `STRIPE_SECRET_KEY` set (rk_live_...)
- [ ] `STRIPE_PUBLISHABLE_KEY` set (pk_live_...)
- [ ] `STRIPE_WEBHOOK_SECRET` set (whsec_..., the real one, not the placeholder)
- [ ] `POSTMARK_SERVER_TOKEN` set
- [ ] `EMAIL_FROM` = `support@panefreequoting.com`
- [ ] `EMAIL_FROM_NAME` = `Panefree Quoting`
- [ ] `ADMIN_EMAIL` set
- [ ] `SENTRY_DSN` set
- [ ] `BACKUP_DESTINATION` set (e.g. `b2://Panefreequoting/snapshots`)
- [ ] `B2_KEY_ID` + `B2_APPLICATION_KEY` set
- [ ] `DATABASE_PATH` = `/var/data/sovereign.db`
- [ ] **NOT SET:** `DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED`

### Third-party state

- [ ] Stripe Dashboard → Webhooks → endpoint pointed at `https://panefree-quoting.onrender.com/webhook/stripe` (will re-point to `panefreequoting.com` post-flip)
- [ ] Stripe Dashboard → Public details → business name = `Lightmade Software`
- [ ] Postmark Dashboard → server is in **Live** state (out of sandbox)
- [ ] Postmark → Sender Signatures → `support@panefreequoting.com` shows ✅ Verified
- [ ] Sentry project receiving events (the test event you triggered during H6 setup is visible)
- [ ] B2 bucket `Panefreequoting` exists and the app key has read+write+delete on it

### Legal docs (verify on the Render auto-URL before flipping DNS)

- [ ] Privacy Policy: no `__________` placeholder, no `/contac` truncation, all links point to `panefreequoting.com/...`
- [ ] Terms of Service: rendered, all links valid
- [ ] Cookie Policy: no "advertising cookies" language, cookie table present, no deprecated cookie names

### Inquisitor gate

- [ ] H7 post-audit verdict: **PASS** (file: `PLANNING/audits/hotfix-7-post-audit.md`)
- [ ] C3 explicitly satisfied (audit document references the gate)

**If ALL of the above are checked: proceed to §2.**

---

## 2. Launch Sequence — DNS Flip

Execute in order. Don't skip steps even if "obvious."

### 2.1 — Record the launch SHA

```powershell
cd C:\Users\Thorn\.openclaw\workspace\projects\window-quoting
git log --oneline -1
```

Write the SHA in `notes/hotfix-7-notes.md` under "Launch SHA." This is the **rollback target** for Tier 1 below.

### 2.2 — Render: add custom domain

1. Render Dashboard → service → **Settings** → **Custom Domains**
2. **+ Add Custom Domain** → enter `panefreequoting.com` → save
3. Render displays the DNS records you need to add (typically a CNAME or A record)
4. Note the exact target hostname / IP Render provides

### 2.3 — Cloudflare: add DNS records

1. Cloudflare → `panefreequoting.com` zone → **DNS** → **Records**
2. Add the records exactly as Render specified
3. **Proxy status:** start with **DNS only** (gray cloud), NOT proxied. Cloudflare's proxy can interfere with Render's Let's Encrypt cert provisioning on first verification.
4. Save

### 2.4 — Wait for Render to verify

- Render's Custom Domains page polls DNS automatically
- Shows ✅ Verified when records propagate (typically 1-15 min)
- Render then provisions a Let's Encrypt cert automatically
- Wait for cert to show as **Active** before continuing

### 2.5 — Repeat for `www.panefreequoting.com`

1. Render → Custom Domains → **+ Add** → `www.panefreequoting.com`
2. Cloudflare → DNS → add the CNAME Render specifies
3. Wait for verification + cert
4. Decide: `www` → redirect to apex, OR apex → redirect to `www`. Stripe support URLs assume apex. Recommend `www` redirects to apex.

### 2.6 — Curl the new domain from your machine

```powershell
curl https://panefreequoting.com/health
curl https://panefreequoting.com/legal/privacy
curl https://panefreequoting.com/legal/terms
curl https://panefreequoting.com/legal/cookies
```

All four must return 200. If any fail, **abort and roll back per §4**.

### 2.7 — Update `APP_BASE_URL` env var

1. Render → Environment → `APP_BASE_URL` → change from `https://panefree-quoting.onrender.com` to `https://panefreequoting.com`
2. Save → triggers redeploy (~2-3 min)
3. Wait for "Listening at..." in logs

### 2.8 — Update Stripe webhook endpoint URL

1. Stripe Dashboard → Developers → Webhooks → click your endpoint
2. **Update details** → change URL to `https://panefreequoting.com/webhook/stripe`
3. Save (signing secret `whsec_...` stays valid, no env var change needed)

### 2.9 — Cloudflare proxy decision (optional)

After Render's cert is provisioned and stable (give it 30 min to be safe):

- Cloudflare DNS records → flip proxy status to **Proxied** (orange cloud) for DDoS protection
- Cloudflare → SSL/TLS → **Full (strict)** mode (NOT Flexible — Flexible re-encrypts and creates a loop with Render's TLS)
- If anything breaks after enabling proxy, flip back to **DNS only** and revisit later

This is optional polish. The site works fine in DNS-only mode.

### 2.10 — Smoke test as a real user

1. Open browser in incognito → `https://panefreequoting.com`
2. Sign up with an email you actually control (not `lightmadeai@gmail.com` — use a personal/secondary address to validate cross-domain Postmark sends now that approval is in)
3. Receive verification email → click link → land on verified account
4. Click `/top-up` → click Starter pack → land on Stripe Checkout
5. **Do NOT actually buy.** Cancel back to `/top-up`. This validates the redirect flow without spending money.
6. Optional: if you do want a $0.01 paid validation, the smallest path is a single Starter pack ($8.99), refund within 5 min. Pure formality at this point — H6 already validated the live billing pipeline.

### 2.11 — Tag `v1.0.0` and push

```powershell
cd C:\Users\Thorn\.openclaw\workspace\projects\window-quoting
git tag -a v1.0.0 -m "Production launch — panefreequoting.com live"
git push origin v1.0.0
```

### 2.12 — Start the watch window (§3)

---

## 3. Active Watch Window (30 minutes minimum)

Start a timer for 30 min from §2.10 smoke test. Check the following surfaces every ~5 minutes during the window:

### What to watch

| Surface | Where | What you're looking for |
|---|---|---|
| Render logs | Render → Logs tab | Any traceback. Especially `ERROR in app:` lines or `[CRITICAL] WORKER TIMEOUT`. |
| Render metrics | Render → Metrics tab | CPU >70% sustained, memory growth, response time spikes |
| Sentry | sentry.io → your project → Issues | Any new issue type appearing after launch SHA |
| Stripe | Stripe Dashboard → Payments | Any payment attempt (should be zero for now — flag if not) |
| Stripe Webhooks | Stripe → Developers → Webhooks → Events | Any 4xx or 5xx response (should be zero — flag if not) |
| `/health` from outside | `curl https://panefreequoting.com/health` | Always 200 with `db: ok` |

### Watch-window pass criteria

After 30 minutes, the launch is **stable** if:

- [ ] Zero new Sentry error issues (info/warning is fine; error level is not)
- [ ] Zero `ERROR in app:` lines in Render logs
- [ ] `/health` returned 200 on every check
- [ ] No CPU sustained >50% (one-shot spikes are fine)
- [ ] No payment activity to investigate (or if there was: it succeeded end-to-end with webhook 200)

If all five hold: **launch is green.** Close watch window. Log the timeline in `notes/hotfix-7-notes.md`.

---

## 4. Rollback Procedure

If something breaks, escalate through tiers in order. Don't jump to Tier 3 unless Tiers 1-2 don't address the issue.

### Tier 1 — Bad code deploy

**When to use:** the latest deploy introduced an error you didn't catch in pre-flight. Site is up but broken in some flow.

**Procedure:**
1. Render → Service → **Manual Deploy**
2. **Deploy a previous version** → select the launch SHA you recorded in §2.1
3. Wait for deploy to complete (~2-3 min)
4. Re-run `/health` curl + smoke test
5. **Estimated time:** 3-5 min

**Notes:**
- This rolls back code only. Env vars, disk contents (DB), Stripe webhook URLs all stay current.
- Safe for any code change that doesn't depend on a non-backward-compatible DB schema (none currently exist).

### Tier 2 — App fundamentally broken

**When to use:** Tier 1 didn't fix it, OR the app is throwing 500s on every route, OR you need to stop serving broken pages immediately while you diagnose.

**Procedure:**
1. Render → Service → **Settings** → scroll to bottom → **Suspend Service**
2. Site immediately returns 503 from Render's edge
3. Diagnose at your pace
4. To resume: **Resume Service** → wait for boot
5. **Estimated time:** 30 sec down + diagnosis time

**Notes:**
- Customers (when there are some) see "503 Service Unavailable" — a clear "down" signal
- DB and disk content survive suspend
- Stripe webhooks during suspension will return 502 from Render — Stripe will retry for ~3 days, so events aren't permanently lost

### Tier 3 — DNS / certificate disaster

**When to use:** the custom domain is broken (cert failed to provision, DNS misconfigured, Cloudflare conflict), site is unreachable via `panefreequoting.com` but the Render auto-URL works.

**Procedure:**
1. Cloudflare → DNS → `panefreequoting.com` records → either:
   - **Delete** the records pointing at Render → site only reachable at `panefree-quoting.onrender.com`, OR
   - **Modify** records to point somewhere else (a "maintenance" host you control)
2. Render → Environment → `APP_BASE_URL` → revert to `https://panefree-quoting.onrender.com` so internal redirects don't loop
3. Stripe → Webhooks → revert endpoint URL to the Render auto-URL
4. **Estimated time:** 5-15 min (TTL propagation)

**Notes:**
- Slowest tier — only use if Tiers 1 and 2 don't apply
- The Render auto-URL remains functional throughout — it's an always-on fallback

### Tier 4 — Total nuclear option

**When to use:** something so wrong you don't want the site reachable at any URL.

**Procedure:**
1. Render → Service → **Suspend Service** (covers all URLs hitting Render)
2. Cloudflare → DNS → delete records for `panefreequoting.com`
3. Investigate from scratch

You should basically never need this. If you reach Tier 4, write a post-mortem in `notes/hotfix-7-notes.md`.

---

## 5. Incident Response Table

Quick reference for known failure modes. Find the symptom, follow the action.

| Symptom | Likely cause | First action | Escalate to |
|---|---|---|---|
| `/health` returns 502 | App not responding / gunicorn down | Render Logs → look for traceback | Tier 2 rollback if no obvious fix |
| `/health` returns 503 with `db: fail` | SQLite locked or disk unmounted | Render → restart service | Check disk mount in Render Disks tab |
| Stripe webhook returning 5xx | Handler bug (cf. H6 Additions 4+5) | Render Logs → grep `[STRIPE-WEBHOOK]` | Tier 1 rollback to prior SHA |
| Stripe webhook returning 400 | Signature mismatch | Re-check `STRIPE_WEBHOOK_SECRET` env var | Re-create webhook in Stripe, update env |
| Signup form 500s | Likely Postmark token or DB issue | Render Logs → look for `[EMAIL-SEND-FAILED]` or DB error | Confirm Postmark approval still active |
| Verification email never arrives | Postmark issue OR `EMAIL_FROM` mismatch | Postmark → Activity → check delivery status | Re-verify sender signature, check approval state |
| Customer sees old "Panefree Quotes" branding | `EMAIL_FROM_NAME` env var not updated | Render → Environment → set to `Panefree Quoting` | Force redeploy |
| Customer card statement shows old descriptor | Stripe descriptor not propagated | Verify Stripe → Settings → Public details → Statement descriptor = `Lightmade Software` | Wait — descriptor changes can take 24h to propagate to card networks |
| Sentry quota burning fast | Loop bug or scraper hitting an error route | Sentry → Issues → identify top issue | Tier 1 rollback or hotfix the noisy route |
| Render CPU pegged | Bot / scraper attack or runaway loop | Render Metrics → confirm | Cloudflare proxy on + rate limit at edge |
| Backup script silent for >25h | Backup heartbeat URL not pinging | Check `BACKUP_HEARTBEAT_URL` env var, then `scripts/backup.py` logs | Re-run backup manually |

---

## 6. Communication Plan

### Internal (operator)

- All decisions, observations, timeline events logged in `notes/hotfix-7-notes.md` as they happen
- Sentry alerts route to `lightmadeai@gmail.com`
- UptimeRobot alerts route to `lightmadeai@gmail.com` (after T6 monitor setup)

### External (customers)

**Current state:** No public communication channel yet. Pre-customer phase.

**Outage protocol while this remains true:**
- Fix silently
- Log the incident timeline in `notes/`
- No social media / email blast / status page

**Future state (post-launch task):**
- Build an email-blast agent for incident notification
- Build a monitoring agent for site-watch
- Both flagged on post-launch roadmap; update this section when they exist

---

## 7. Tag & Close-Out

After watch window passes:

### 7.1 — Confirm `v1.0.0` tag is on origin

```powershell
git fetch --tags
git tag -l v1.0.0
```

Should show `v1.0.0`. If not, re-push: `git push origin v1.0.0`.

### 7.2 — Write the launch-day notes

`PLANNING/notes/hotfix-7-notes.md` should include:

- Launch SHA (from §2.1)
- DNS flip start time (from §2.3)
- Render verification timestamp (from §2.4)
- First `/health` success on `panefreequoting.com` (from §2.6)
- Smoke test outcome (from §2.10)
- Watch window start + end timestamps
- Any incidents (or "none — clean launch")
- Tag application timestamp

### 7.3 — Update sprint state

1. `PLANNING/current-sprint.md` → mark Hotfix-7 status `done`, audit_status `pending`
2. Move sprint manifest to `PLANNING/done/hotfix-7.md`
3. Notify Inquisitor for post-audit

### 7.4 — Update project registry

`C:\Users\Thorn\.openclaw\workspace\shared\projects.md` → Window Quoting status updates to "Launched 2026-XX-XX — `v1.0.0` live at panefreequoting.com"

---

## 8. Post-Launch Priorities (Reference, not part of this runbook)

These are deferred work that becomes urgent **after** the launch is stable, NOT during the watch window:

- **Cookie policy `__cfduid` deprecation** (Termly fix — H6 R4, H7 audit R3)
- **`gunicorn.conf.py` docstring fix** (H6 R5)
- **Per-product Stripe statement descriptors** (`statement_descriptor_suffix="PANEFREE"`)
- **Tailwind CDN → compiled CSS** (H7 T5, deferred per Inquisitor R1)
- **UptimeRobot monitors** (H7 T6 — set up after DNS is stable so `/health` URL is correct)
- **Monitoring agent build** (Chris's pending project)
- **Email-blast agent build** (Chris's pending project)
- **Redis-backed rate limiter + multi-worker gunicorn** (when traffic justifies — 20+ paying customers OR sustained p95 >500ms)
- **Brand domain `lightmadesoftware.com` purchase** (umbrella site)
- **Migrate secrets from `C:\Users\Thorn\secrets\panefree-prod.txt` to a password manager** (Bitwarden recommended)
- **`test_account_lifecycle.py`** (H3 R2 — still owed)
- **`[BACKUP-*]` log tags in DEPLOYMENT.md** (H5 R1 — still owed)
- **App-level functional restore test** (H5 R4 — still owed)

---

## 9. Inquisitor C3 — Satisfaction Statement

This runbook exists to satisfy Inquisitor Condition C3 (carried verbatim from Hotfix-6):

> "Post-audit before DNS flip is MANDATORY. The audit IS the launch gate. No DNS flip until Inquisitor issues a PASS on the full hotfix-7 sprint."

**Compliance gate:**

- [ ] Inquisitor's post-audit on Hotfix-7 issued **PASS** verdict
- [ ] Verdict committed to `PLANNING/audits/hotfix-7-post-audit.md`
- [ ] Chris read the verdict and acknowledged any non-blocking remarks

**Only after the box above is checked does §2 (DNS flip) become authorized.** The Go/No-Go checklist (§1) re-checks this as its final gate.

---

**End of runbook.**
