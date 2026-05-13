# Hotfix-6 — T1 Implementation Guide: Production WSGI + ProxyFix

**Target:** Claude (or human executor)
**Branch:** `hotfix-6` off current `main`
**Project root:** `projects/window-quoting/`

## Context

The Panefree Quoting app (Flask) currently runs in dev mode (`python app.py` → `app.run(debug=True, port=5001)`). T1 makes it production-ready with gunicorn + ProxyFix + a proper gunicorn config file. The app is deploying to Render (or similar PaaS) with a reverse proxy terminating TLS.

## What Already Exists

- `app.py` — Flask app at line 191 (`app = Flask(__name__)`)
- `config.py` — All config via env vars; `DEV_MODE` controls dev-only escape hatches
- `requirements.txt` — All deps except gunicorn (not yet added)
- `DEPLOYMENT.md` §8 — Documents gunicorn command and ProxyFix snippet
- `legal/` directory — `privacy-policy.html`, `terms-of-service.html`, `Cookie Policy.txt`
- ProxyFix import is NOT yet in app.py (currently just documented in DEPLOYMENT.md)
- `scripts/backup.py` and `scripts/restore.py` — H5 backup/restore scripts

## Files to Create/Modify

### 1. NEW: `gunicorn.conf.py`

```python
"""Gunicorn configuration for Panefree Quoting production deployment.

Start with 2 workers (single-worker is fine for v1 traffic; 2 gives
zero-downtime restarts). 30s timeout matches DEPLOYMENT.md §8.
Access log to stdout (hosting provider captures it).
"""

import os

# Workers: start conservative for v1. Scale up when traffic warrants.
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:5001")

# Pre-load app for faster worker boot; set after fork for DB connections
preload_app = False
```

### 2. MODIFY: `app.py` — Add ProxyFix (after line ~257, after Limiter init)

Insert AFTER the `limiter = Limiter(...)` block and BEFORE the Talisman block (~line 260):

```python
# Hotfix-6 T1: ProxyFix for reverse proxy headers.
# Without this, request.remote_addr = proxy IP (rate limiter gates
# entire site on one bucket). x_for=1 = one trusted proxy layer.
# DEPLOYMENT.md §8 has the explanation and the no-ProxyFix failure mode.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
```

**IMPORTANT:** This MUST go after `limiter` init (line ~257) because the limiter reads `request.remote_addr`, and ProxyFix mutates that attribute. If ProxyFix wraps before limiter init, the limiter's `key_func=get_remote_address` resolves correctly at request time.

### 3. MODIFY: `requirements.txt` — Add gunicorn

Add after the `b2sdk~=2.12.0` line:

```
# --- WSGI server (Hotfix-6 T1) ---
gunicorn~=23.0.0
```

### 4. NEW: Flask routes for legal pages

Create `app.py` routes (or a new `legal_routes.py` blueprint — either works, but a blueprint is cleaner):

```python
# Hotfix-6: Legal page routes (Privacy Policy, Terms, Cookie Policy)
# Static HTML served from legal/ directory. Post-launch: swap to Termly embed.

from flask import render_template_string, abort
import os

LEGAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legal")

@app.route("/legal/privacy")
def legal_privacy():
    path = os.path.join(LEGAL_DIR, "privacy-policy.html")
    if not os.path.exists(path):
        abort(404)
    with open(path, "r", encoding="utf-8") as f:
        return render_template_string(f.read())

@app.route("/legal/terms")
def legal_terms():
    path = os.path.join(LEGAL_DIR, "terms-of-service.html")
    if not os.path.exists(path):
        abort(404)
    with open(path, "r", encoding="utf-8") as f:
        return render_template_string(f.read())

@app.route("/legal/cookies")
def legal_cookies():
    path = os.path.join(LEGAL_DIR, "cookie-policy.html")
    if not os.path.exists(path):
        abort(404)
    with open(path, "r", encoding="utf-8") as f:
        return render_template_string(f.read())
```

**Note:** `Cookie Policy.txt` needs to be renamed/converted to `cookie-policy.html` before this route works. Chris is handling this in Termly — the file should be exported as HTML matching the format of the other two.

### 5. MODIFY: `legal/Cookie Policy.txt` → `legal/cookie-policy.html`

Rename and convert to HTML matching the format of `privacy-policy.html` and `terms-of-service.html`. Chris is currently completing this in Termly. Once exported, drop it in `legal/` as `cookie-policy.html`.

## Acceptance Criteria Checklist

- [ ] `gunicorn.conf.py` exists with 2 workers, 30s timeout, access log to stdout
- [ ] `ProxyFix` wired in `app.py` after limiter init (before Talisman)
- [ ] `gunicorn` added to `requirements.txt`
- [ ] Legal routes `/legal/privacy`, `/legal/terms`, `/legal/cookies` return 200
- [ ] `legal/cookie-policy.html` exists (converted from `.txt`)
- [ ] `python -m gunicorn -c gunicorn.conf.py app:app` starts successfully
- [ ] TLS termination verified at proxy (HTTP → HTTPS redirect, no redirect loops)
- [ ] `request.remote_addr` shows real client IP, not proxy IP
- [ ] Talisman `force_https` works with ProxyFix (no redirect loops)
- [ ] H6 prerequisites checkbox: "Privacy Policy + Terms of Service + Cookie Policy hosted at `/legal/*`" can be checked

## Testing Notes

```bash
# Start gunicorn locally
cd projects/window-quoting
pip install -r requirements.txt
python -m gunicorn -c gunicorn.conf.py app:app

# Verify routes
curl -s http://127.0.0.1:5001/legal/privacy | head -5
curl -s http://127.0.0.1:5001/legal/terms | head -5
curl -s http://127.0.0.1:5001/legal/cookies | head -5

# Verify ProxyFix (needs a proxy in front to test X-Forwarded-For)
# For now: check that the app starts without error and the import is present
grep -n "ProxyFix" app.py
```

## Render-Specific Notes

On Render, gunicorn is typically the default start command. Add to Render dashboard:
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -c gunicorn.conf.py app:app`
- **Environment:** Set all vars from H6-T2 (secrets list)

Render handles TLS termination and reverse proxy automatically. The `ProxyFix` x_for=1 setting matches Render's single proxy layer.

## Non-Blocking Remarks Carried Forward

- H3 R1: `.env.example` missing H3 env vars
- H5 R1: `[BACKUP-*]` tags not in DEPLOYMENT.md log catalog
- H5 R3: Schema dumps accumulate without prune (negligible v1)