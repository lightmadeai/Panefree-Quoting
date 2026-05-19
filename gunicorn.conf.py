"""Gunicorn configuration for Panefree Quoting production deployment.

Hotfix-6 T1: Production WSGI server configuration.

Start with 1 worker — override via GUNICORN_WORKERS env var (conservative
for v1 traffic; gives zero-downtime restarts). 30s timeout matches DEPLOYMENT.md §8. Access log to stdout
so the hosting provider (Render) captures it in their log pipeline.

Worker count and bind address are configurable via environment variables
so we can tune post-launch without a code change.
"""

import os

# Workers: start conservative for v1. Scale up when traffic warrants.
# On Render, GUNICORN_WORKERS can be set in the environment.
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:5001")

# Pre-load app disabled so DB connections are created per-worker after fork.
preload_app = False