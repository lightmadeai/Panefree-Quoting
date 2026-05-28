# Deployment Guide — Window Cleaning Engine

This document covers everything required to take a fresh checkout to a working production deployment. Sprint 5 will add the live-environment specifics (Stripe live keys, HTTPS termination, monitoring); Sprint 4's contribution is the code-side, environment templates, and lessons learned.

---

## 1. Environment variables

All configuration lives in `config.py` and reads from `os.environ` at boot. Copy `.env.example` to `.env` and fill in real values.

| Variable | Required for | Notes |
|---|---|---|
| `SRE_SECRET_KEY` | Production | Cryptographically random, 32+ bytes. Used as Flask `SECRET_KEY` for session signing. The dev default in `config.py` is intentionally insecure — fail loud in prod if not set (see "Pre-flight checks"). |
| `STRIPE_SECRET_KEY` | Live billing | `sk_live_...` in production. Absence triggers Stripe-disabled fallback paths in `/checkout` and `/account/billing-portal`. |
| `STRIPE_PUBLISHABLE_KEY` | Live billing | `pk_live_...` in production. Surfaced to `top_up.html` for client-side Stripe.js. |
| `STRIPE_WEBHOOK_SECRET` | Live billing | `whsec_...` from the Stripe Dashboard for the production endpoint. Required by `/webhook/stripe` for signature verification. |
| `APP_BASE_URL` | Live billing | Externally-resolvable URL. Stripe `success_url` / `cancel_url` are built from this; misconfiguring it sends customers to localhost. |
| `DEV_MODE` | Dev only | `1` / `true` / `yes` enables the `/dev/grant-credits` simulator AND disables `SESSION_COOKIE_SECURE` + Talisman `force_https`/HSTS so plain-HTTP localhost works. Hard-gated: simulator route 404s when `STRIPE_SECRET_KEY` is set. **NEVER set in production** — it's the kill switch for three different prod-only protections. |
| `WTF_CSRF_DISABLED` | Test only | `1` disables CSRF token enforcement so the existing `testing/stress_probe.py` + locust harness POSTs work without per-form token fetches. Loud `WARNING` logged at boot when set. **NEVER set in production.** |
| `RATELIMIT_DISABLED` | Test only | `1` disables Flask-Limiter so locust can hammer `/login`/`/register` without tripping the IP gate. **NEVER set in production.** |
| `SOFT_CAP_THRESHOLD` | Optional | Annual subscribers' soft-cap notice fires at this number of quotes per billing period. Default 1000. The 80% warning is computed from this value (`threshold * 8 // 10`). |
| `SUPPORT_EMAIL` | Optional | Surface address for the contact CTA + footer. Default `support@panefreequoting.com` (Hotfix-4 T0 — was `support@windowquoting.com` pre-domain-decision). |
| `RATE_LIMIT_QUOTES_PER_HOUR` | Optional | Free-tier quote-generation rate limit per rolling 60-min window. Default 10. Separate from the Hotfix-2 Flask-Limiter gates on auth routes. |

---

## 2. Pre-flight checks before going live

Run these in order. If any fails, do not deploy.

### 2.1 Secret key is set and not the dev default
```bash
python -c "import config; assert config.SECRET_KEY != 'sre_secret_key_change_me_in_prod', 'DEV SECRET KEY IS LIVE — abort'"
```

### 2.2 Stripe is configured (or explicitly accepted as test-mode)
```bash
python -c "import config; print('STRIPE_SECRET_KEY:', 'SET' if config.STRIPE_SECRET_KEY else 'MISSING')"
```
Sprint 5 swaps test → live keys. Until then, deployments run in test-mode and the simulator route may be useful.

### 2.3 Database backup
```bash
cp sovereign.db sovereign.db.bak-pre-deploy-$(date +%Y%m%d-%H%M%S)
```

### 2.4 Schema-parity check
The database schema must match what `models.py` declares. See "Lesson: schema parity" below for why.

```bash
python - <<'EOF'
import sqlite3, sys
from app import app, db
from sqlalchemy import inspect
with app.app_context():
    insp = inspect(db.engine)
    for tbl in db.metadata.tables.values():
        live_cols = {c["name"] for c in insp.get_columns(tbl.name)}
        model_cols = {c.name for c in tbl.columns}
        only_live = live_cols - model_cols
        only_model = model_cols - live_cols
        if only_live or only_model:
            print(f"DRIFT in {tbl.name}: only_live={only_live} only_model={only_model}")
            sys.exit(1)
print("OK: schema matches model")
EOF
```

If this prints `DRIFT`, **stop**. See the "Schema parity" section below before proceeding.

### 2.5 Output directory + legacy PDF migration (Hotfix-1 T3)

The `output/` tree (per-user PDF buckets) is created on demand by `_user_pdf_dir()`, but a fresh deployment should pre-create it so first-run permission errors don't surface mid-request:

```bash
mkdir -p output && chmod 750 output
chown <app-user>:<app-group> output
```

Confirm `.gitignore` excludes the tree (it should — line 17 covers `output/`):

```bash
git check-ignore output/ && echo "OK: output/ is gitignored"
```

**One-time legacy PDF migration.** Before Sprint 4's BUG-008 fix, `/generate` wrote PDFs to `project_root/`. Those files are unreachable through the post-fix `/download` route. Run the migration script once to sweep them into a quarantine subdirectory of `output/`:

```bash
python scripts/migrate-pdfs.py --dry-run    # preview
python scripts/migrate-pdfs.py              # apply
```

The script is idempotent — second run is a no-op. It does NOT attribute legacy files to specific users (the Quote table never recorded the rendered filename, so the mapping doesn't exist). Files land in `output/_legacy_unattributed/` for archival/forensic use.

### 2.6 Stress probe passes
```bash
python app.py &
SERVER_PID=$!
sleep 3
python testing/stress_probe.py
kill $SERVER_PID
```
All probes must report PASS / expected status codes. Any FAIL is a deployment blocker.

### 2.7 No debug statements in production code
Sprint 4 T5 cleared these; re-grep before each deploy:
```bash
grep -nrE "print\(|console\.log\(" --include="*.py" --include="*.html" --include="*.js" .
```

### 2.8 Security headers + CSRF smoke (Hotfix-2 T2 + T4)

Spin the app, log in, then hit a state-changing route without a CSRF token — Flask-WTF must reject it. The response headers from Talisman must be present:

```bash
# Start under production env (DEV_MODE unset)
python -m gunicorn -b 127.0.0.1:5001 app:app &
SERVER_PID=$!
sleep 2

# CSRF: form POST without token must 400
curl -s -o /dev/null -w "POST /login (no csrf) -> %{http_code} (want 400)\n" \
  -X POST -d "email=a@b.test&password=test1234" http://127.0.0.1:5001/login

# Headers: CSP + HSTS + X-Frame + X-Content-Type + Referrer-Policy
curl -sI http://127.0.0.1:5001/login | grep -iE \
  "content-security-policy|strict-transport-security|x-frame-options|x-content-type-options|referrer-policy"

kill $SERVER_PID
```

Expected: `400` on the CSRF probe, all five headers in the grep output. Missing CSP or HSTS is a deployment blocker — re-check `DEV_MODE` is unset and Talisman initialized.

**Expected `Content-Security-Policy` value (post-Hotfix-10):**

```
default-src 'self';
script-src 'self' js.stripe.com;
style-src 'self' 'unsafe-inline' fonts.googleapis.com;
font-src 'self' fonts.gstatic.com;
img-src 'self' data:;
connect-src 'self' api.stripe.com;
frame-src js.stripe.com;
frame-ancestors 'none';
base-uri 'self';
form-action 'self' checkout.stripe.com
```

CSP timeline (worth knowing if a future audit asks "why this allowlist"):
- **Hotfix-2** (2026-05-11) — initial Talisman CSP. `script-src` was `'self' 'unsafe-inline' cdn.tailwindcss.com js.stripe.com`.
- **Hotfix-8** (2026-05-19) — added `'unsafe-inline'` to `script-src` to unblock the inline scripts in `index.html` after they regressed under CSP. Temporary measure; logged as tech debt.
- **Hotfix-9a** (2026-05-19) — removed `cdn.tailwindcss.com` after Tailwind moved to build-time compile (see §8.5). `script-src` became `'self' 'unsafe-inline' js.stripe.com`.
- **Hotfix-10** (2026-05-26) — externalized all 4 inline `<script>` blocks in `index.html` to `static/js/{quote-form,profile-loader,pdf-download}.js`, then removed `'unsafe-inline'` from `script-src`. `script-src` is now `'self' js.stripe.com` — minimum viable for our deploy. **Any future regression that re-adds `'unsafe-inline'` should be flagged in code review.**

`style-src 'unsafe-inline'` is still present — every page template carries an inline `<style>body { font-family: 'Inter', sans-serif; }</style>` block. Removing it requires a nonce/hash approach (or moving the rule to `output.css`). Deferred to a future hardening sprint.

### 2.9 Dependency vulnerability scan

```bash
pip install pip-audit
pip-audit --requirement requirements.txt
```

A clean run (no `WARN`/`FOUND VULNS`) is required to deploy. If pip-audit flags anything, bump the affected pin in `requirements.txt` and re-run.

---

## 3. File system layout (production)

```
project_root/
├── app.py, config.py, engine.py, generator.py, models.py, notices.py
├── sovereign.db                     # SQLite — on a backed-up volume
├── output/                          # Generated PDFs (BUG-008 fix)
│   ├── 1/                           # User-id-keyed buckets
│   │   ├── quote_<rand>.pdf
│   │   └── invoice_<rand>.pdf
│   ├── 2/
│   │   └── ...
│   └── _legacy_unattributed/        # Hotfix-1 T3 quarantine (pre-BUG-008 PDFs)
├── templates/                       # Jinja2
├── static/                          # served by Flask (or upstream nginx)
│   ├── css/
│   │   ├── input.css                # Tailwind directives, source (H9a)
│   │   └── output.css               # Compiled build artifact, gitignored (H9a)
│   ├── img/
│   │   ├── logo.svg                 # Fiverr logo, original colors (H9b)
│   │   └── logo-light.svg           # White-wordmark variant for dark nav (H9b)
│   └── js/                          # H10 externalized scripts (CSP: 'self')
│       ├── nav.js                   # Mobile drawer toggle (H9b)
│       ├── quote-form.js            # Form-state persistence + URL rewrite (H10)
│       ├── profile-loader.js        # populateRates + new-profile panel (H10)
│       └── pdf-download.js          # PDF download + invoice convert (H10)
├── package.json, tailwind.config.js # Build pipeline for static/css/output.css (H9a)
├── node_modules/                    # Build-time only, gitignored (H9a)
└── PLANNING/, testing/              # Not served
```

The `static/js/` files are loaded via `<script defer src="...">` from `index.html` and `_nav.html`. They MUST remain `'self'`-served for CSP `script-src` to keep its post-H10 minimum-viable allowlist (see §2.8). Any new client-side script — including third-party widgets — should land in `static/js/` and be referenced by `url_for('static', filename='js/...')`, not pasted inline.

**The `output/` directory must be writable** by the application user but **not** accessible via any web-server alias. The `/download/<filename>` route is the only legitimate way to fetch PDFs and pins lookups to the caller's own bucket. See "BUG-008 architecture" below.

---

## 4. BUG-008 architecture (per-user PDF buckets)

This is the most security-relevant piece of the Sprint 4 work and worth understanding before any future routing changes.

**Pre-Sprint-4 design (broken):**
- All PDFs lived in `project_root/`
- `/download/<filename>` did `os.path.basename(filename)` then served `os.path.join(project_root, basename)`
- Any logged-in user could download `sovereign.db`, `app.py`, `.env`, or any other file in `project_root`

**Post-Sprint-4 design:**
- PDFs live in `output/<user_id>/<filename>`
- `_user_pdf_dir(current_user.id)` returns `<OUTPUT_DIR>/<user_id>/` and creates it on demand
- `/download/<filename>` resolves `<user_id_dir>/<basename>` and `abort(404)` on miss
- The `user_id` comes from the session, never from the URL — so a leaked filename from user A is unreachable when user B is logged in
- The bucket directory contains only PDFs that user has generated — `sovereign.db`, source files, etc. are not in any user's bucket

**Defenses in depth:**
1. `os.path.basename()` strips path traversal (`..`, leading slash)
2. Per-user prefix isolates filename namespaces
3. Bucket contents are PDFs only — no source or DB
4. 404 (not 403) on miss avoids leaking whether a filename exists for some other user

Future routing changes that touch `/download/` or PDF storage **must preserve all four defenses**.

---

## 5. Lesson: schema parity (from BUG-001)

**What happened (Sprint 4 walkthrough, BUG-001):** A column (`users.total_recovered_value`) had been added to the SQLite schema in Sprint 1 but later removed from `models.py` during a refactor. The column survived as `NUMERIC NOT NULL` with no `DEFAULT`, so any INSERT that didn't explicitly set it (which the model could no longer do, since the column wasn't on the User class) violated the constraint. **Result: signup was completely broken** until the column was dropped from the live DB.

**Why it slipped through:** The project uses `db.create_all()` + a manual `_ensure_table_columns()` helper rather than versioned migrations (Alembic, Flask-Migrate, etc.). `db.create_all()` only creates tables it doesn't already see — it never drops columns or detects model-vs-DB drift. `_ensure_table_columns()` only adds; it doesn't compare.

**What to do about it:**
1. **Run the schema-parity check (Section 2.4) before every deploy.** It uses SQLAlchemy's `inspect()` to compare live columns against `db.metadata` and exits non-zero on drift.
2. **When removing a column from a model**, also drop it from the DB in the same change set — don't leave the column behind. SQLite 3.35+ supports `ALTER TABLE ... DROP COLUMN` natively. Older SQLite needs the rebuild dance.
3. **Sprint 5 candidate:** introduce Alembic. The current model has 4 sprints' worth of `_ensure_table_columns` calls; that won't scale. Alembic gives each schema change a versioned migration file you can review, rerun, and roll back.

---

## 6. Smoke test post-deploy

After deploying, hit these in order with a real browser:

1. `GET /register` — should render
2. Register a new account — should succeed (verifies BUG-001 stays fixed)
3. Log in
4. Verify the email via the URL printed in the app log
5. Hit `/` — should redirect to `/profiles/new` (BUG-003 fix)
6. Create a profile, return to `/`, generate a quote
7. Open the resulting PDF — confirm `QUOTE #Q-000001` in the header (BUG-007), no `(Custom Rate)` in line items (BUG-006)
8. Convert to invoice — confirm `INVOICE #INV-000001`
9. Try `GET /download/sovereign.db` while logged in — must return 404 (BUG-008)
10. Run all 4 Stripe payment flows (test-mode in Sprint 4; live-mode in Sprint 5)

A failure on any of #2, #5, #6, #7, #9 is a deployment blocker.

---

## 7. Rollback plan

The pre-deploy DB backup from Section 2.3 is the rollback point. To revert:

1. Stop the application
2. `cp sovereign.db.bak-pre-deploy-<timestamp> sovereign.db`
3. `git checkout <previous-tag>` (or whatever the prior known-good revision is)
4. Restart

The `output/<user_id>/` directories are append-only from the app's perspective; rolling the DB back orphans the PDFs generated since the backup, but doesn't break anything — they simply aren't referenced by any Quote row.

---

## 8. WSGI server (Hotfix-2 §L4)

**Never run `python app.py` in production.** The `if __name__ == "__main__":` block at the bottom of `app.py` calls `app.run(debug=True, ...)` which is single-threaded, leaks tracebacks to the client, and is explicitly documented by Flask as unsafe for production. Use gunicorn:

```bash
gunicorn --workers 4 --bind 127.0.0.1:5001 --access-logfile - --error-logfile - app:app
```

Behind a reverse proxy (nginx/Caddy), the proxy terminates TLS and passes `X-Forwarded-For` upstream. Flask-Limiter's IP-keyed buckets read `request.remote_addr`, which defaults to the proxy's IP — wrap the app with `werkzeug.middleware.proxy_fix.ProxyFix` so `X-Forwarded-For` is honored:

```python
# In app.py, after app = Flask(__name__):
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
```

Without `ProxyFix`, every request looks like it came from the proxy's single IP — the rate limiter would gate the entire site on one global bucket. Configure `x_for=N` where N is the number of trusted proxies in front of the app (usually 1).

---

## 8.5 Asset pipeline — Tailwind CSS (Hotfix 9a)

Pre-Hotfix-9a, every page loaded `<script src="https://cdn.tailwindcss.com">` — Tailwind's JIT compiler running in the user's browser (~400 KB of JS per page, slow FCP, widened CSP attack surface). Hotfix 9a moves Tailwind to a build-time compile that emits a single static `static/css/output.css` (~21 KB minified, gzipped further by Render's CDN).

### What runs at build time

Render's `buildCommand` (see `render.yaml`) chains three steps:

```
pip install -r requirements.txt   # Python deps
npm install                       # Node deps (tailwindcss@3.4.x only)
npm run build:css                 # tailwindcss -i input.css -o output.css --minify
```

The compiled output lands at `static/css/output.css` and is served by Flask's `static/` route. Templates reference it via `<link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">`.

### What's NOT in git

`static/css/output.css` and `node_modules/` are gitignored. `output.css` is a build artifact — regenerated from `static/css/input.css` + `tailwind.config.js` + `templates/**/*.html` on every deploy. Never edit `output.css` by hand.

### Local dev workflow

When editing templates locally and you want CSS changes reflected immediately:

```bash
npm install                # one-time
npm run dev:css            # runs tailwindcss --watch in the foreground
```

The watch mode rebuilds `output.css` on every file save. Run it in a separate terminal alongside `python app.py`. If you don't run it, your local pages will reference a stale or missing `output.css` — most likely you'll see an unstyled page until you run `npm run build:css` once.

### Updating `tailwind.config.js`

The config has two important arrays:

- **`content`** — globs Tailwind scans for class names. Currently `./templates/**/*.html` (excluding `templates/email/`) and `./static/js/**/*.js`. If you add a new template directory or JS source, add its glob here.
- **`safelist`** — classes that must be in the compiled CSS even if Tailwind's scanner doesn't find them in source. Currently 6 classes from `templates/index.html`'s `classList.add/remove` calls. See `PLANNING/research/class-audit.md` for the full audit. If you add new `classList.*` calls or build class strings via JS string concat, audit the new classes and add them here.

### CSP interaction (Hotfix 10 boundary)

Hotfix 9a removes `cdn.tailwindcss.com` from `script-src` (it's no longer needed — the CDN was the only third-party script source). Hotfix 10 then externalized the inline `<script>` blocks in `index.html` to `static/js/` and removed `'unsafe-inline'` from `script-src`. Post-H10, `script-src` is `'self' js.stripe.com` — see §2.8 for the full timeline. `style-src 'unsafe-inline'` stays for now (templates have inline `<style>` blocks with the Inter font-family declaration); deferred to a future hardening sprint.

---

## 9. Log catalog (Hotfix-4 T3)

Every `app.logger.warning` and `app.logger.error` line in `app.py` carries a structured `[TAG]` prefix so log searches are deterministic. This catalog is the source of truth for "what does this log line mean and how do I respond." Sentry alert rules (Operations runbook §10) key off these tags.

| Tag | Level | Meaning | Suggested response |
|---|---|---|---|
| `[CSRF]` | WARNING | `WTF_CSRF_DISABLED=1` set at boot — test escape hatch active | If seen in production: deploy is misconfigured; unset the env var and restart |
| `[MAIL]` (disabled) | WARNING | `MAIL_DISABLED=1` set at boot — no emails will send | If seen in production: deploy is misconfigured; unset the env var and restart |
| `[MAIL]` (token missing) | ERROR | `POSTMARK_SERVER_TOKEN` unset in production | Set `POSTMARK_SERVER_TOKEN` and restart — new users can't satisfy email_verified gate |
| `[REGISTER-SUCCESS]` | INFO | New account created | Forensic / funnel metric — no action |
| `[LOGIN-SUCCESS]` | INFO | User logged in | Forensic — no action |
| `[EMAIL-VERIFICATION]` | INFO | Verification token issued or re-issued | Forensic — verify URL captured as fallback if email failed |
| `[EMAIL-SENT]` | INFO | Postmark accepted a transactional message | Forensic — Postmark dashboard is canonical |
| `[EMAIL-SEND-FAILED]` | ERROR | Postmark rejected or network call failed | Check Postmark dashboard, verify `POSTMARK_SERVER_TOKEN` + `EMAIL_FROM` sender signature |
| `[MAIL-DISABLED]` | INFO | Would-have-sent line from mailer in test mode | Forensic; should never appear in prod |
| `[PASSWORD-RESET]` | INFO | Reset request received (issued, completed, or no-op for unknown email) | Forensic; high volume of unknown-email requests = enumeration probe → investigate IP |
| `[ACCOUNT-DELETED]` | INFO | User self-deleted their account | Forensic audit trail; one record per deletion |
| `[ACCOUNT-DELETE-PDF-CLEANUP]` | WARNING | PDF bucket cleanup failed after account delete | Manually `rm -rf output/<user_id>/` on the host |
| `[CONTACT-SUBMISSION]` | INFO | Custom-plan inquiry from soft-cap CTA | Also emailed to `ADMIN_EMAIL` (T5/H3); reply same-day |
| `[CREDIT-REFUND-FAILED]` | ERROR | `/generate` failed AND credit refund UPDATE also failed | Also emailed to `ADMIN_EMAIL`; manually `+1 credit_balance` on the user_id |
| `[STRIPE-WEBHOOK]` | INFO | Signature-verified webhook event received | Forensic — pair with Stripe Dashboard event log via event_id |
| `[STRIPE-CANCEL-FAILED]` | ERROR | Account delete proceeded but Stripe sub cancel API failed | Also emailed to `ADMIN_EMAIL`; manually cancel the subscription in Stripe Dashboard |
| `[SENTRY-RATE-LIMITED]` | stderr | More than 500 events/hour to Sentry — drops happening | Investigate the underlying error storm; consider Sentry plan upgrade |
| `[BACKUP-UPLOADED]` | stdout | Daily backup binary + schema dump uploaded successfully | Forensic — pair with heartbeat ping for full success signal |
| `[BACKUP-DONE]` | stdout | Backup pipeline completed (snapshot + upload + prune + heartbeat) | Forensic — terminal success line |
| `[BACKUP-PRUNED]` | stdout | Retention prune removed an old backup | Forensic; high volume = retention policy working as designed |
| `[BACKUP-FAILED]` | stderr + email | Backup pipeline failed at some stage (snapshot, upload, or prune) | Email auto-fires to ADMIN_EMAIL; investigate via stage name in payload, re-run manually after fix |
| `[BACKUP-ALERT-FAILED]` | stderr | Admin alert email itself failed to send after a BACKUP-FAILED | Check Postmark dashboard; non-fatal (cron exit code still flags the underlying failure) |
| `[BACKUP-HEARTBEAT-FAILED]` | stderr | Backup succeeded but the UptimeRobot heartbeat ping failed | Non-fatal; check `BACKUP_HEARTBEAT_URL` env + UptimeRobot dashboard. Backup itself was successful. |

**Where they go:** all `app.logger.*` calls emit to gunicorn's stdout/stderr in production. The hosting provider (Render / etc.) captures and rotates these — see Operations runbook (§10) for the log retention configuration.

**What's NOT in the catalog:** routine 200 responses, debug-level lines, framework logs (werkzeug request lines, SQLAlchemy queries). Sentry handles uncaught exceptions; log catalog handles deliberate observability.

---

## 10. Operations runbook (Hotfix-4 T4)

This section is the operator-facing manual for running this software in production. It covers (a) external monitoring setup, (b) reactive playbooks for the most likely incidents, and (c) the proactive maintenance schedule.

### 10.1 External monitoring setup

#### UptimeRobot

1. Sign in to UptimeRobot, click **+ New Monitor**.
2. Monitor type: **HTTP(s)**.
3. Friendly name: `Panefree Quoting — /health`.
4. URL: `https://panefreequoting.com/health`.
5. Monitoring interval: **5 minutes** (free tier minimum; sufficient for v1).
6. Alert contacts: your email (and SMS if you've enabled it). Default channels work.
7. Save.

UptimeRobot does a GET on `/health` every 5 minutes. The endpoint returns 200 + `{"db":"ok"}` when healthy; 503 + `{"db":"fail"}` when the database is unreachable. Any non-200 triggers an alert email within ~2 minutes.

Add a second monitor for the backup heartbeat once H5 ships — see Hotfix-5 §T4.

#### Sentry alert rules

In Sentry's project settings → Alerts → **+ Create Alert Rule**, set up the following three rules:

| Rule | Condition | Action |
|---|---|---|
| Error storm | An event is seen more than **5 times in 1 hour** | Email me |
| Payment failure | An event with tag `[CREDIT-REFUND-FAILED]` OR `[STRIPE-CANCEL-FAILED]` more than **1 time in 1 hour** | Email me (same-day reconcile) |
| Latency regression | Transaction p95 duration is more than **2 seconds for 15 minutes** | Email me |

Mobile push notifications: install the **Sentry mobile app** (free, iOS + Android) and connect to your account. SMS / Twilio not used in v1 per Inquisitor C2.

#### Postmark monitoring (manual)

Postmark's own dashboard is the source of truth for email delivery. Check weekly:
- **Activity → Sent** for failed sends
- **Activity → Bounces** for any unusual rates (>2% sustained = problem)
- **Activity → Spam complaints** — should be near-zero for transactional mail

No automated alerts wired in v1 — Postmark has them in their dashboard if you want to set them.

### 10.2 Alert → response playbook

For each common alert, the "investigate → mitigate → fix" sequence:

#### `[CREDIT-REFUND-FAILED]` (also emails ADMIN_EMAIL)
1. **Investigate.** Open the email or grep logs for `[CREDIT-REFUND-FAILED]` — pull `user_id`, `original_error`, `refund_error`.
2. **Mitigate.** Manually add 1 credit:
   ```bash
   sqlite3 sovereign.db "UPDATE users SET credit_balance = credit_balance + 1 WHERE id = <USER_ID>"
   ```
   Email the user: "Heads up — we hit a snag generating your last quote. Your credit has been restored."
3. **Fix.** If `refund_error` shows a pattern (DB lock, disk full, sqlite busy), file a sprint to investigate root cause. One-offs from transient sqlite contention are acceptable; sustained patterns are not.

#### `[STRIPE-CANCEL-FAILED]` (also emails ADMIN_EMAIL)
1. **Investigate.** The user account is already deleted; the Stripe sub may still be billing them. Email shows `sub_id`.
2. **Mitigate.** Log in to Stripe Dashboard → Subscriptions → search by `sub_id` → Cancel subscription. Issue any pro-rated refund if appropriate.
3. **Fix.** Usually a one-off Stripe API hiccup. If pattern, check Stripe service status and API key validity.

#### `[EMAIL-SEND-FAILED]` (no auto-email — log only)
1. **Investigate.** Check Postmark dashboard for the recipient's send attempts. Look for bounces, spam-complaint flags, or 4xx responses.
2. **Mitigate.** If a specific recipient is bouncing, the user's email is wrong or full — no app-side fix possible. If many recipients are failing, check `POSTMARK_SERVER_TOKEN` validity and `EMAIL_FROM` sender signature.
3. **Fix.** Token rotation or signature re-verification in Postmark.

#### `/health` returning 503 (UptimeRobot alert)
1. **Investigate.** SSH or open the hosting console. `curl https://panefreequoting.com/health` and read the response. If `db=fail`, the SQLite file is unreachable.
2. **Mitigate.** Check disk space (`df -h`), check the gunicorn process is up, check that `sovereign.db` exists at the expected path. If sqlite was locked by a backup, the lock auto-releases.
3. **Fix.** If the DB is gone, restore from latest H5 backup (see Hotfix-5 §T3 restore drill).

#### Sentry error storm
1. **Investigate.** Open the top unresolved event in Sentry. The stack trace + request context tell you what's wrong.
2. **Mitigate.** If the bug is user-facing (e.g. /generate is 500-ing), consider rolling back to the last known-good deploy. See §7 Rollback plan.
3. **Fix.** File a hotfix sprint with the Sentry event ID in the manifest.

### 10.3 Maintenance schedule (proactive)

Calendar-driven, not incident-driven. Logged in `MAINTENANCE_LOG.md` (repo root) on each pass.

| Cadence | Task | Time |
|---|---|---|
| **Weekly** (Monday) | Skim Sentry unresolved errors. Skim gunicorn 5xx in access logs. Check Stripe Dashboard for failed payments / disputes. Glance at signup + quote volume (DB query or Stripe). | 15-30 min |
| **Monthly** (1st of month) | Run `pip-audit --requirement requirements.txt --strict`. Bump any flagged deps in `requirements.txt`. Re-run `testing/stress_probe.py` + locust. Redeploy. Review Sentry quota usage (free tier = 5k errors/month). | 1-2 hours |
| **Quarterly** (Jan / Apr / Jul / Oct 1st) | Full re-run of `stress_probe.py` + locust + `pip-audit`. Execute one full backup restore drill (H5 §10.3). Read Stripe Dashboard tax / payout summary. Re-read this DEPLOYMENT.md for stale instructions. | 2-4 hours |
| **Annually** (each January) | Major-version upgrades (Flask N → N+1, Python 3.x → 3.x+1). TLS cert renewal verification (auto-renew should handle, but verify). Re-run the full pre-launch security review. Archive prior year's backups beyond retention to cold storage if desired. | 1 day |
| **Reactive** | Customer reports a bug → triage same day → fix within the week. Security / billing reports → same-day fix, no exceptions. | Variable |

Append an entry to `MAINTENANCE_LOG.md` for every scheduled pass with date + what was done + anomalies noted. Skipped entries are visible gaps.

### 10.4 On-call rotation (solo ops for v1)

One-person ops for v1 — Thorn IS the rotation. Honestly-named expectations:
- **Phone on bedside table at night** for critical alerts (Sentry "payment failure" + UptimeRobot 503).
- **Realistic SLA**: acknowledged within 4 business hours, fixed within 2 business days for non-billing/non-security issues.
- **Security or billing report**: same-day fix, regardless of hours.
- **Set customer expectations on the contact form accordingly** — a small "we respond within 1 business day" note pre-empts angry follow-ups.

When the operator role grows beyond one person (e.g. you hire someone), this section gets a real rotation schedule + escalation contact list. For now it's just an honest statement of where the buck stops.

---

## 11. Backups + restore drill (Hotfix-5)

SQLite is a single file. Losing it = losing every user, profile, quote, and transaction record. Stripe holds canonical billing data; reconstructing user identity + their business profiles from invoice metadata is a multi-week disaster. This section covers (a) the daily-backup automation, (b) the retention policy, (c) the restore procedure, and (d) the once-per-quarter drill.

### 11.1 Daily backup automation

`scripts/backup.py` runs the full pipeline: SQLite `.backup` (atomic online snapshot) → schema dump → gzip → upload to `BACKUP_DESTINATION` → retention prune → heartbeat ping.

**Required env vars** (set in your hosting secrets store):

| Var | Source | Notes |
|---|---|---|
| `BACKUP_DESTINATION` | choose | `b2://bucket-name/optional-prefix` (recommended per Inquisitor C1) |
| `B2_KEY_ID` | Backblaze console → App Keys | Scope key to the single backup bucket |
| `B2_APPLICATION_KEY` | Backblaze console → App Keys | Paired with `B2_KEY_ID` |
| `BACKUP_HEARTBEAT_URL` | UptimeRobot Heartbeat URL | Optional; if unset, no ping (alerting reduced) |

**Scheduling** depends on host:

| Host | How |
|---|---|
| **Render** | Add a Cron Job: command `python scripts/backup.py`, schedule `0 3 * * *` (daily 03:00 UTC), share env vars with the web service |
| **Railway** | Similar; create a Cron Job under the service, set schedule via Railway dashboard |
| **DO Droplet / Linode VPS** | `crontab -e` and add:<br/>`0 3 * * * cd /opt/window-quoting && /usr/bin/python3 scripts/backup.py >> /var/log/window-quoting-backup.log 2>&1` |

**Expected behavior:**
- Runtime: ~10 seconds for a small DB (<100 MB). Grows linearly with DB size.
- Storage cost: ~3.6 GB / year of daily binary backups = $0.02/mo on B2 (well within free tier).
- Schema dumps add ~10-20 KB each = negligible.

### 11.2 Retention policy

`scripts/backup.py` prunes the destination after each upload (skip with `--skip-prune`):

| Slot | Kept | Window |
|---|---|---|
| Daily | All backups | Last 7 days |
| Weekly | Earliest per ISO-week | Days 7-34 (~4 weeks) |
| Monthly | Earliest per calendar month | Last 6 months |
| Older | — | Deleted |

Implemented as a pure function (`compute_retention_set`) with 10 unit tests in `testing/test_retention.py`. **First production run should use `--dry-run`** to confirm the prune list before any deletes are real:

```bash
BACKUP_DESTINATION=b2://my-bucket python scripts/backup.py --dry-run
```

### 11.3 Restore procedure

`scripts/restore.py` is the inverse pipeline: download → gunzip → sanity check → schema parity check → write.

**Standard restore (DR scenario):**

```bash
# 1. Restore to a sandbox path first — NEVER overwrite live sovereign.db
#    on the first attempt
python scripts/restore.py \
  "b2://my-bucket/sovereign-YYYYMMDD-HHMMSS.db.gz" \
  /tmp/restore-test.db

# 2. Sanity-check the restored file
python -c "
import sqlite3
c = sqlite3.connect('/tmp/restore-test.db')
for t in ('users', 'quotes', 'pricing_profiles', 'transactions'):
    print(t, c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
"

# 3. If the row counts look right, stop the app and swap files:
systemctl stop window-quoting    # or your host's equivalent
cp sovereign.db sovereign.db.pre-restore-$(date +%Y%m%d-%H%M%S)
cp /tmp/restore-test.db sovereign.db
systemctl start window-quoting

# 4. Verify the app boots and serves /health
curl https://panefreequoting.com/health
```

`restore.py` refuses to overwrite `project_root/sovereign.db` directly unless `--force` is passed. The "restore to /tmp first, manually swap" pattern is intentional — gives an inspection window before pointing the live app at restored data.

### 11.4 Quarterly restore drill

**Run on the 1st of Jan / Apr / Jul / Oct.** Documented in `testing/restore-drill-YYYY-MM.md` (current: `testing/restore-drill-2026-05.md`). Procedure:

1. Pick a backup from at least a week ago (proves retention is working)
2. Restore to `/tmp/restore-test.db` via `scripts/restore.py`
3. Confirm row counts match a known-good live snapshot
4. Confirm schema parity check passed (restore.py exits 0, not 4)
5. (Optional) Boot the Flask app pointed at the restored DB via env override, run `stress_probe.py`
6. Tear down `/tmp/restore-test.db`
7. Append a new section to the drill report file (or rotate the file if it grows large)

The May 2026 drill ran end-to-end during Hotfix-5 T3 — see the drill report for the row-count match.

### 11.5 Alerting

Two layers, wire-compatible with Hotfix-4's observability stack:

1. **Sentry capture on backup script crash.** `scripts/backup.py` calls `sentry_sdk.capture_exception` on any non-zero exit AND sends an admin email via `_notify_admin` (Hotfix-3 T5). Catches "the cron ran but the script crashed mid-run."
2. **UptimeRobot Heartbeat on successful backup.** `BACKUP_HEARTBEAT_URL` is pinged at the end of every successful run. Configure UptimeRobot to alert if no ping arrives within **36 hours** — gives one missed day + recovery window before paging. Catches "cron daemon died silently," which Sentry can't see because the script never ran.

**Setup steps for the UptimeRobot side:**
1. UptimeRobot → + New Monitor → type: **Heartbeat**
2. Friendly name: `Panefree Quoting — daily backup`
3. Interval: 36 hours (so one missed day doesn't page; two does)
4. Copy the generated heartbeat URL into `BACKUP_HEARTBEAT_URL` in your hosting secrets
5. Set alert contacts the same as the /health monitor (§10.1)

---

## 12. Open items for Sprint 5

These are intentionally not in Sprint 4's scope:

- Live Stripe key swap and real-card validation purchase
- HTTPS enforcement (web server / reverse proxy config) — Talisman `force_https` already redirects, but the proxy needs the TLS termination + cert
- Production monitoring / alerting (uptime, webhook failure rate, payment failure rate)
- Versioned migrations (Alembic) — see "Schema parity" lesson above
- Per-environment configuration files (test / staging / prod)
- Database backup automation (currently manual)
- Flask-Limiter Redis storage backend (currently `memory://` — won't share state across gunicorn workers; per-worker buckets are 4× more permissive than intended)
- `werkzeug.middleware.proxy_fix.ProxyFix` wired in `app.py` (currently documented in §8 but not committed)
