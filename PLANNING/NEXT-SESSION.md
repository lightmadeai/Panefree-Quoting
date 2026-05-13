# Next-Session Handoff — 2026-05-13

**For:** the next Claude Code session Chris spins on this project.
**Purpose:** zero-context bootstrap to the live state without re-deriving
six hotfixes worth of history. Read this first.

---

## Where the project is

**Stabilize phase, 5 of 6 hotfixes shipped, H6 (production cutover) is next.**

```
H1 ✅ PASS merged — Email verification + deployment polish
H2 ✅ PASS merged — Pre-production security hardening
H3 ✅ PASS merged — User access lifecycle (Postmark, password reset, account delete)
H4 ✅ PASS merged — Observability (Sentry, /health, ops runbook + maintenance schedule)
H5 ✅ PASS merged — Backups + restore drill + schema dump
H6 ⏳ READY in drafts/  — Production cutover (the launch sprint)
```

Master branch is at the H5 merge commit. `git log --oneline -3`:
```
6806c2d Merge hotfix-5: Backups + Restore Drill + Schema Dump
39298c6 hotfix-5 close-out: audit_status -> pass after PASS verdict
3a99608 hotfix-5 post-audit: PASS verdict + R1 fix + protocol §5.11 amendment
```

`pip-audit --strict` clean. All 34 unit tests pass. stress_probe 13/13. Locust 30u × 45s = 0 failures.

---

## What H6 is

Production cutover sprint. Pre-approved draft at `PLANNING/drafts/hotfix-6.md`. Tasks (per the manifest):

- **T1** — Production WSGI + reverse proxy + `ProxyFix` middleware (gunicorn config, TLS termination at the proxy, HTTP→HTTPS redirect via Talisman)
- **T2** — Production environment variables (set all the prod env vars in the hosting secrets store; confirm DEV_MODE/WTF_CSRF_DISABLED/RATELIMIT_DISABLED/MAIL_DISABLED are NOT set; run pre-flight checks)
- **T3** — Flask-Limiter Redis storage (only if multi-worker — gated on the gunicorn config choice in T1)
- **T4** — Live Stripe smoke test (real card purchase of Starter pack + Annual sub, then refund — Chris executes)
- **T5** — `LAUNCH.md` checklist + 30-min watch window + rollback plan

Plus the protocol amendment (§5.11) means auto-promotion happens — Jade may have already moved H6 to `current-sprint.md` by the time you read this. Check.

---

## What's waiting on Chris (external, not code)

Per `PLANNING/chris-sprint.md` (Chris's private tracker — DO NOT modify):

- Phase 1 (accounts) ✅ — Postmark, Sentry, UptimeRobot, B2 all signed up with keys saved
- Phase 2 (DNS) — DKIM/SPF/Return-Path on `panefreequoting.com` already done per his last check-in
- Phase 3 (Stripe live keys for THIS app, not Resumeforge's) — pending; Chris generates a restricted key set scoped to the panefreequoting.com webhook endpoint
- Phase 4 (Legal pages: Privacy + Terms at `/legal/privacy` and `/legal/terms`) — files exist in `legal/` dir (untracked; ask Chris where he wants them committed)
- Phase 5 (Launch day procedure) — `LAUNCH.md` is T5 deliverable

Domain is `panefreequoting.com`. Support email is `support@panefreequoting.com`. Brand name in customer-facing copy is "Panefree Quotes" (NOT "Window Quoting" — the internal codename `window-quoting` stays everywhere it appears in code paths / log tags / Stripe metadata).

---

## How to start the next session

1. **Read this file.** You're already doing that.
2. **Check `PLANNING/current-sprint.md`.** Per §5.11 auto-promotion, this should be hotfix-6 by now. If it still says hotfix-5, ask Chris if Jade has done the promotion.
3. **Read `PLANNING/drafts/hotfix-6.md`** — the full pre-approved manifest with Inquisitor conditions baked in.
4. **Read the recent done files for context:**
   - `PLANNING/done/hotfix-5.md` — what just shipped
   - `PLANNING/notes/hotfix-5-notes.md` — design decisions, especially the platform-fragile file URL parsing in `scripts/backup.py` (you'll touch backup again indirectly via H6 cron config)
5. **Confirm git state:** `git branch --show-current` should show `master`. `git status` should show `chris-sprint.md`, `proposals/`, `legal/` as untracked (all intentional — Chris's stuff, leave alone).

Don't auto-start H6. Wait for Chris's go.

---

## Env vars accumulated so far (`.env.example` is authoritative)

| Source sprint | Vars |
|---|---|
| Sprint 1-4 | `SRE_SECRET_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `APP_BASE_URL`, `SUPPORT_EMAIL`, `SOFT_CAP_THRESHOLD`, `RATE_LIMIT_QUOTES_PER_HOUR` |
| H2 | `DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED` (test kill switches — NEVER in prod) |
| H3 | `POSTMARK_SERVER_TOKEN`, `EMAIL_FROM`, `EMAIL_FROM_NAME`, `ADMIN_EMAIL`, `MAIL_DISABLED` (test kill switch) |
| H4 | `SENTRY_DSN` |
| H5 | `BACKUP_DESTINATION`, `B2_KEY_ID`, `B2_APPLICATION_KEY`, `BACKUP_HEARTBEAT_URL` |
| H6 (deferred) | `REDIS_URL` (if multi-worker), `VERSION` file at project root (deploy script writes git SHA) |

---

## Patterns to know about

### Option (b) for live smoke tests
H3 (Postmark), H4 (Sentry), H5 (B2) all built with kill-switch env vars (`MAIL_DISABLED`, no `SENTRY_DSN`, `file://` backup target) so in-sprint testing doesn't need real credentials. Chris runs the live smoke himself post-deploy. H6 T4 (live Stripe) is the one place this pattern breaks — Chris executes the real-card test himself.

### Test kill switches → NEVER in prod
`DEV_MODE`, `WTF_CSRF_DISABLED`, `RATELIMIT_DISABLED`, `MAIL_DISABLED` all bypass production protections. The pre-flight check in DEPLOYMENT.md §2.1 explicitly greps for them. Loud `WARNING` logs at boot if set.

### `testing/stress/run_server.py` sets all four kill switches via `os.environ.setdefault`
This is intentional — the test harness needs them. Production runs `gunicorn`, never this script. Don't worry about it leaking to prod.

### Auto-promotion §5.11 (NEW from H5 post-audit)
Post-audit PASS with no hard blockers → Jade auto-promotes next sprint without manual wait. Held when CONTESTED.

---

## Known carry-forward items (not blocking)

- **H3 R2:** `testing/test_account_lifecycle.py` doesn't exist. Deferred to ops sprint or post-launch. Currently `stress_probe.py` covers the paths.
- **H4 R1:** Sentry rate cap is per-worker, not per-DSN. Acceptable for v1 single-digit-worker.
- **H4 R2:** `/health` doesn't probe Stripe/Postmark/Sentry. Intentional — those are external dep failures, not app failures.
- **H5 R3:** Schema dumps accumulate without prune (~5 MB/year). Trivial.
- **H5 R4:** No app-level functional restore drill. Optional quarterly extension.

Backlog has P4 "Dynamic Add-Ons" — explicitly post-launch.

---

## Things NOT to touch

- `PLANNING/chris-sprint.md` — Chris's private tracker
- `PLANNING/proposals/` — superseded by `drafts/` after Jade adoption; informational only
- `legal/` — Chris's Phase 4 work; he chooses when/where to commit
- `CHANGELOG.md` historical entries — leave the old `support@windowquoting.com` references alone (historical record)
- Internal codename `window-quoting` (folder, log tags, Stripe metadata) — only the user-visible brand changed to "Panefree Quotes"

---

## Quick state-check commands

```bash
cd C:/Users/Thorn/.openclaw/workspace/projects/window-quoting
git log --oneline -5
git status
python -m pytest testing/test_mailer.py testing/test_sentry_hooks.py testing/test_health.py testing/test_retention.py
pip-audit --requirement requirements.txt --strict
cat PLANNING/current-sprint.md
```

If all of those look clean, the project is exactly where this handoff says it is.
