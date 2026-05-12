---
label: hotfix-2
project: window-quoting
phase: stabilize
drafted_by: Claude (per Chris blanket approval, 2026-05-11)
status: in-progress
created: 2026-05-11
audit_status: pending
audit_note: "Drafted post-security-review during a single-session execution per Chris's blanket approval (2026-05-11). Pre-audit deferred to post-execution at Chris's discretion — Inquisitor receives final state for verdict."
---

# Hotfix-2 — Pre-Production Security Hardening

## Why

Pre-prod security pass (2026-05-11) surfaced 3 HIGH and 4 MEDIUM gaps in deployment-config hardening. None are code defects per se — all are missing defense-in-depth layers that need to be in place before live Stripe keys + HTTPS cutover. Locust stress test (5057 reqs, 0 failures) confirmed app logic is solid; this sprint closes the config gaps. See the conversation transcript for the full audit.

Reference findings:
- H1: SESSION_COOKIE_SECURE / HTTPONLY / SAMESITE not set in config.py
- H2: No CSRF protection on 16 state-changing POST forms
- H3: `_ensure_table_columns` interpolates table name into raw SQL (not user-reachable today, but fragile)
- M1: No global / IP-based rate limit on /login, /register, /verify
- M2: Missing security response headers (CSP, HSTS, X-Frame-Options, etc.)
- M3: No password upper bound (pbkdf2 DoS surface)
- M4: register.html minlength="6" disagrees with server's 8-char check
- M6: `_user_pdf_dir` makedirs uses umask-default mode

## Goals

- All HIGH and MEDIUM findings closed (or explicitly accepted with a written deferral note)
- No regressions vs Hotfix-1 — `testing/stress_probe.py` still PASSes all probes, locust harness still 0-failure
- DEPLOYMENT.md pre-flight checklist updated to cover the new config knobs
- `requirements.txt` committed for reproducible deploys + future `pip-audit` scans

## Tasks

### T1 — Cookie hardening + register password minlength

**Acceptance:**
- `config.py` sets `SESSION_COOKIE_SECURE = True`, `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`. Comment explains the prod requirement.
- For local dev (no HTTPS) the SECURE flag would block login cookies; gate it through an env var (`SESSION_COOKIE_SECURE` defaults True in prod, False if `DEV_MODE=1`).
- `templates/register.html` `<input minlength="6">` → `<input minlength="8">` to match server-side `_password_strength_error`.
- Manual verification: login cookie inspected in browser dev tools shows `Secure; HttpOnly; SameSite=Lax` flags when not in DEV_MODE.

### T2 — CSRF protection via Flask-WTF

**Acceptance:**
- `Flask-WTF` added to deps; `CSRFProtect(app)` initialized in `app.py`.
- Every POST form in `templates/*.html` carries `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- `/webhook/stripe` explicitly exempted via `@csrf.exempt` (Stripe signs the body; it can't provide a session CSRF token).
- A `<meta name="csrf-token" content="{{ csrf_token() }}">` is rendered in every page, and any AJAX call (`/generate` from `index.html`, etc.) sends the token via `X-CSRFToken` header.
- Verification: a POST to `/contact` (or any other form) with no token returns 400; with the token returns 200/302.

### T3 — Defensive bounds

**Acceptance:**
- `_ensure_table_columns` rejects any `table_name` not in a hardcoded allowlist (`{"users", "quotes"}` today). Assertion fires before the f-string SQL ever runs.
- `_password_strength_error` rejects `len(password) > 128` with a clear message — closes the pbkdf2 DoS surface.
- `_user_pdf_dir` calls `os.makedirs(d, mode=0o700, exist_ok=True)` and chmods existing dirs to `0o700` on first touch (defensive — the umask default of 0o755 / 0o777 is too loose on a shared host).

### T4 — Rate limiting + security headers

**Acceptance:**
- `Flask-Limiter` added; default-exempt with explicit decorators on /login (10/min), /register (5/min), /verify (10/min), /contact (5/min), /checkout (10/min). All limits IP-keyed.
- `Flask-Talisman` added with a Content Security Policy that allows: self, `cdn.tailwindcss.com`, `fonts.googleapis.com`, `fonts.gstatic.com`, `js.stripe.com`, `api.stripe.com`, plus `'unsafe-inline'` for style-src (template <style> blocks need it; script-src does NOT get unsafe-inline).
- Response headers verified on `/login`: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`.
- Talisman `force_https=True` unless `DEV_MODE=1` (matches the cookie-secure gating in T1).
- Local dev unaffected: with `DEV_MODE=1` the server still accepts HTTP and cookies still work without HTTPS.

### T5 — Reproducible deps + deploy notes

**Acceptance:**
- `requirements.txt` committed with pinned versions for all runtime deps (Flask, Flask-Login, Flask-SQLAlchemy, Flask-WTF, Flask-Limiter, Flask-Talisman, stripe, fpdf2, etc.). Generated via `pip freeze`-filtered-to-runtime, not the dev test deps.
- `DEPLOYMENT.md` updated:
  - New env vars documented (`DEV_MODE` clearly disables prod-only protections)
  - Pre-flight check 2.8 — security headers smoke test (curl + grep for CSP/HSTS)
  - Pre-flight check 2.9 — `pip-audit` clean
  - Section 11 — "Never run `python app.py` in prod; use a real WSGI server (gunicorn/uwsgi)"

## Out of scope

- Alembic / versioned migrations (deferred — see Sprint 5 candidate in DEPLOYMENT.md §5)
- Audit log table for credit transactions (L3 — deferred, billing already idempotent)
- Production WSGI server selection + config (Ops tier, Sprint 5)
- HTTPS / reverse proxy config (Ops tier, Sprint 5)
- Webhook secret rotation policy (Ops tier, Sprint 5)

## definition of done

- All T1-T5 acceptance criteria met
- `testing/stress_probe.py` passes all probes against the hardened server (with DEV_MODE=1 so HTTPS doesn't bite the test)
- Locust harness re-run shows 0 failures and the same per-tier behavior (rate-limit clamp on free, sub bypass works)
- `requirements.txt` reflects the actual import surface (no dev-only deps polluting prod)
- Notes file at `PLANNING/notes/hotfix-2-notes.md` captures any design decisions / deferrals
- All commits on `hotfix-2` branch
