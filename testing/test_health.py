"""
Unit tests for the Hotfix-4 T2 /health endpoint.

Covers the happy path (200 + db=ok) and the DB-down path (503 + db=fail).
DB failure is simulated by patching db.session.execute to raise rather
than physically taking the SQLite file offline — SQLite on Windows holds
an exclusive lock while the app process is up, so file-level tests don't
work cross-platform. Mocking the failure at the SQLAlchemy boundary
exercises the same try/except branch.
"""
import json
from unittest.mock import patch

import pytest

import app


@pytest.fixture
def client():
    """Test client wrapper that requests over HTTPS so Talisman's
    force_https redirect (set in Hotfix-2 T4) doesn't 302 the probe.
    Production keeps the redirect; tests bypass it because they're
    not actually negotiating TLS."""
    app.app.config["TESTING"] = True
    return app.app.test_client()


# base_url makes Flask's test client see the request as coming in over
# HTTPS, bypassing Talisman's redirect. All test calls go through this.
HTTPS = {"base_url": "https://localhost"}


def test_health_happy_path_returns_200(client):
    resp = client.get("/health", **HTTPS)
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"] in ("dev", None) or isinstance(body["version"], str)
    assert isinstance(body["uptime_s"], int)
    assert body["uptime_s"] >= 0


def test_health_returns_503_when_db_fails(client):
    """Patch db.session.execute to raise so the health endpoint's
    try/except hits the degraded path."""
    with patch("app.db.session.execute", side_effect=Exception("simulated DB outage")):
        resp = client.get("/health", **HTTPS)
    assert resp.status_code == 503
    body = json.loads(resp.data)
    assert body["status"] == "degraded"
    assert body["db"] == "fail"
    # Version + uptime still reported even when DB is down — those are
    # process-local and don't depend on the database.
    assert "version" in body
    assert isinstance(body["uptime_s"], int)


def test_health_does_not_require_auth(client):
    """No session cookie, no Authorization header — health is for
    uptime monitors that have no credentials."""
    resp = client.get("/health", **HTTPS)
    assert resp.status_code == 200
    # Confirm no 302 redirect to /login.


def test_health_returns_json_content_type(client):
    resp = client.get("/health", **HTTPS)
    assert resp.content_type.startswith("application/json")


def test_health_uptime_increases(client):
    """Uptime in second call must be >= first call. Sanity check on
    the time.monotonic() math."""
    import time
    resp1 = client.get("/health", **HTTPS)
    time.sleep(1.1)
    resp2 = client.get("/health", **HTTPS)
    body1 = json.loads(resp1.data)
    body2 = json.loads(resp2.data)
    assert body2["uptime_s"] >= body1["uptime_s"] + 1
