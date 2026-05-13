"""
Unit tests for the Hotfix-4 T1 Sentry before_send hook.

Tests the two custom behaviors in app._sentry_before_send:
  1. PII scrub — password / csrf_token / customer_email / customer_phone
     / customer_address replaced with "[scrubbed]" in request data.
  2. Token-bucket rate limit — caps Sentry to 500 events/hour/worker
     so a Day-1 loop bug can't burn through the free-tier quota.

No live Sentry calls — the hook is pure (event in, event-or-None out)
and we exercise it directly.
"""
import time

import pytest

import app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test starts with a full bucket so rate-limit assertions are
    deterministic."""
    app._sentry_rate_state["tokens"] = float(app._SENTRY_RATE_CAP_PER_HOUR)
    app._sentry_rate_state["last_refill"] = time.monotonic()
    # Reset drop counter so the [SENTRY-RATE-LIMITED] log line doesn't
    # leak across tests (it's a module-level int).
    app._sentry_drops_since_log = 0
    yield


def _event_with_data(**fields):
    """Build a minimal Sentry event dict with the given fields in
    request.data — the bucket the scrub touches."""
    return {"request": {"data": dict(fields)}}


def test_scrub_password_field():
    event = _event_with_data(password="hunter2", normal_field="keep")
    out = app._sentry_before_send(event, {})
    assert out["request"]["data"]["password"] == "[scrubbed]"
    assert out["request"]["data"]["normal_field"] == "keep"


def test_scrub_customer_pii_fields():
    event = _event_with_data(
        customer_email="user@example.com",
        customer_phone="555-1234",
        customer_address="123 Main St",
        normal_field="keep",
    )
    out = app._sentry_before_send(event, {})
    assert out["request"]["data"]["customer_email"] == "[scrubbed]"
    assert out["request"]["data"]["customer_phone"] == "[scrubbed]"
    assert out["request"]["data"]["customer_address"] == "[scrubbed]"
    assert out["request"]["data"]["normal_field"] == "keep"


def test_scrub_csrf_token():
    event = _event_with_data(csrf_token="abc.def.ghi", other="x")
    out = app._sentry_before_send(event, {})
    assert out["request"]["data"]["csrf_token"] == "[scrubbed]"
    assert out["request"]["data"]["other"] == "x"


def test_scrub_case_insensitive():
    """Field-name matching is case-insensitive so a header like
    `Password` or `Customer_Email` also gets scrubbed."""
    event = {"request": {"headers": {"Password": "p", "Customer_Email": "e"}}}
    out = app._sentry_before_send(event, {})
    assert out["request"]["headers"]["Password"] == "[scrubbed]"
    assert out["request"]["headers"]["Customer_Email"] == "[scrubbed]"


def test_scrub_handles_missing_request_section():
    """Events without a request section (e.g. background tasks) shouldn't
    crash the hook."""
    event = {"exception": {"values": [{"type": "RuntimeError"}]}}
    out = app._sentry_before_send(event, {})
    # Hook returned the event unchanged (and didn't raise).
    assert out is not None


def test_rate_limit_drops_event_when_bucket_empty():
    """Drain the bucket; the next event should be dropped (returns None)."""
    app._sentry_rate_state["tokens"] = 0.5  # less than 1 token
    out = app._sentry_before_send(_event_with_data(), {})
    assert out is None


def test_rate_limit_allows_when_bucket_full():
    app._sentry_rate_state["tokens"] = float(app._SENTRY_RATE_CAP_PER_HOUR)
    out = app._sentry_before_send(_event_with_data(), {})
    assert out is not None
    # One token consumed.
    assert app._sentry_rate_state["tokens"] < app._SENTRY_RATE_CAP_PER_HOUR


def test_rate_limit_refills_over_time():
    """After waiting one full refill interval, the bucket should have
    gained ~1 token."""
    app._sentry_rate_state["tokens"] = 0.0
    # Pretend last_refill was 2 intervals ago — should refill 2 tokens.
    app._sentry_rate_state["last_refill"] = (
        time.monotonic() - 2 * app._SENTRY_TOKEN_REFILL_INTERVAL_S
    )
    out = app._sentry_before_send(_event_with_data(), {})
    # After refill of ~2 tokens, one is consumed -> ~1 token remaining.
    assert out is not None
    assert app._sentry_rate_state["tokens"] >= 0.9  # ~1.0 within float jitter


def test_rate_limit_drop_counter_increments():
    """The drop counter tracks how many events were rejected since the
    last log line. Useful for ops to see the volume of dropped events
    without each drop spamming the log."""
    app._sentry_rate_state["tokens"] = 0.0
    # Pin last_refill to "just now" so no refill happens between drops.
    app._sentry_rate_state["last_refill"] = time.monotonic()
    app._sentry_drops_since_log = 0
    for _ in range(3):
        out = app._sentry_before_send(_event_with_data(), {})
        assert out is None
    # First drop logs immediately, then increments without logging until
    # the next 100-multiple. Counter must be at 3 after three drops.
    assert app._sentry_drops_since_log == 3


def test_read_version_sha_falls_back_to_dev_when_no_file():
    """When VERSION file doesn't exist, _read_version_sha returns 'dev'."""
    # This test assumes no VERSION file in project_root during test runs.
    # If a future deploy script writes one, this test will read whatever's
    # in it — that's fine, the assertion only locks in the no-file behavior.
    import os
    version_path = os.path.join(app.project_root, "VERSION")
    if not os.path.exists(version_path):
        assert app._read_version_sha() == "dev"
