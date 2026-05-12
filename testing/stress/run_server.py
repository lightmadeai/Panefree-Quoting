"""
Stable single-process Flask server for stress testing.
Threaded, no debug auto-reload, no use_reloader. Port 5001.

CSRF is auto-disabled for the test run via WTF_CSRF_DISABLED=1 so the
existing locustfile + stress_probe don't have to grab tokens per request.
Production MUST NOT set this var — CSRF correctness is verified
independently by a curl smoke check (DEPLOYMENT.md §2.8).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

# Test-only escape hatches — set BEFORE importing app so app.py sees them.
os.environ.setdefault("WTF_CSRF_DISABLED", "1")
os.environ.setdefault("DEV_MODE", "1")  # also disables SESSION_COOKIE_SECURE for plain-HTTP local

import logging
logging.getLogger("werkzeug").setLevel(logging.WARNING)

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, threaded=True, debug=False, use_reloader=False)
