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
| `DEV_MODE` | Dev only | `1` / `true` / `yes` enables the `/dev/grant-credits` simulator. Hard-gated: simulator route 404s when `STRIPE_SECRET_KEY` is set, so leaving `DEV_MODE=1` in prod is non-fatal but should still be unset for hygiene. |
| `SOFT_CAP_THRESHOLD` | Optional | Annual subscribers' soft-cap notice fires at this number of quotes per billing period. Default 1000. The 80% warning is computed from this value (`threshold * 8 // 10`). |
| `SUPPORT_EMAIL` | Optional | Surface address for the contact CTA + footer. Default `support@windowquoting.com`. |
| `RATE_LIMIT_QUOTES_PER_HOUR` | Optional | Free-tier rate limit per rolling 60-min window. Default 10. |

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
└── PLANNING/, testing/              # Not served
```

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

## 8. Open items for Sprint 5

These are intentionally not in Sprint 4's scope:

- Live Stripe key swap and real-card validation purchase
- HTTPS enforcement (web server / reverse proxy config)
- Production monitoring / alerting (uptime, webhook failure rate, payment failure rate)
- Versioned migrations (Alembic) — see "Schema parity" lesson above
- Per-environment configuration files (test / staging / prod)
- Database backup automation (currently manual)
