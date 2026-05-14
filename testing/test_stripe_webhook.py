"""
Hotfix-7 T7 — Stripe webhook regression test.

Run from project root:
    python -m pytest testing/test_stripe_webhook.py -v

Covers the bug class surfaced in Hotfix-6 Additions 4 + 5:

  stripe.Webhook.construct_event() returns a stripe.Event which is a
  StripeObject — dict-LIKE (supports [key]) but does NOT expose .get().
  Calling event.get("id") triggers StripeObject.__getattr__ which falls
  back to __getitem__ on the string "get", raises KeyError, and the
  wrapping AttributeError ("AttributeError: get") propagates as a 500.
  Every defensive .get() in the handler chain would crash the same way.

  H6 fix (app.py): convert event_obj to a plain dict via to_dict_recursive()
  before dispatch, so downstream handlers can use dict.get() as written.

This test prevents recurrence by using REAL StripeObject instances built
via stripe.Event.construct_from(). Dict fixtures would silently pass
even if the bug came back — that's why this file exists at all.

Coverage:
  - checkout.session.completed (payment mode) — credits land on user
  - customer.subscription.deleted — sub_status flips to "canceled"
  - The exact failure mode regression: a real StripeObject MUST flow
    through the handler without AttributeError on .get()
"""
import json
import os
import tempfile
from unittest.mock import patch

import pytest
import stripe

# Make sure the app picks up a temp SQLite path BEFORE importing app.
# Otherwise app.py opens the real DB and tests pollute it.
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
os.environ["DATABASE_PATH"] = _tmp_db.name
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_only_not_used_because_construct_event_is_mocked"
# DEV_MODE=1 has side effects (disables HTTPS-required cookies, exposes
# the credit simulator). We DON'T want it — these tests run through HTTPS
# via test_client base_url override, same pattern as test_health.py.

import app  # noqa: E402
from models import db, User  # noqa: E402


HTTPS = {"base_url": "https://localhost"}


@pytest.fixture
def client():
    """Flask test client with a freshly-initialized DB. Each test starts
    from an empty users table so credit-balance assertions are deterministic.
    """
    app.app.config["TESTING"] = True
    with app.app.app_context():
        # Wipe + reinit. SQLite truncate via drop_all + create_all is
        # fastest and avoids cross-test state.
        db.drop_all()
        db.create_all()
    yield app.app.test_client()


@pytest.fixture
def test_user():
    """Insert a verified user with the H6 starting credit balance (10)."""
    with app.app.app_context():
        u = User(
            email="webhook-test@panefreequoting.test",
            password_hash="bcrypt$dummy$irrelevant_for_this_test",
            credit_balance=10,
            email_verified=True,
        )
        db.session.add(u)
        db.session.commit()
        uid = u.id
    return uid


def _build_checkout_session_completed_event(user_id: int, credits: int = 10, amount_cents: int = 899):
    """
    Construct a REAL stripe.Event (StripeObject), not a dict.

    This is the critical mechanic of the test: if a future code change
    reintroduces .get() access on the raw event payload, this test will
    fail with the same AttributeError that brought down H6 in production.
    Dict fixtures would mask the regression.
    """
    payload = {
        "id": "evt_test_checkout_completed",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session_id",
                "object": "checkout.session",
                "mode": "payment",
                "client_reference_id": str(user_id),
                "metadata": {
                    "user_id": str(user_id),
                    "pack_id": "starter",
                    "credits": str(credits),
                },
                "amount_total": amount_cents,
                "currency": "usd",
                "payment_status": "paid",
            }
        },
    }
    # construct_from is Stripe SDK's canonical way to build a real Event /
    # StripeObject from a raw dict — same code path construct_event takes
    # internally after signature verification.
    return stripe.Event.construct_from(payload, "sk_test_unused_api_key")


def _build_subscription_deleted_event(sub_id: str):
    """Real StripeObject for subscription cancellation."""
    payload = {
        "id": "evt_test_sub_deleted",
        "object": "event",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": sub_id,
                "object": "subscription",
                "status": "canceled",
                "cancel_at_period_end": False,
                "current_period_end": 9999999999,  # far future, untouched per handler comment
            }
        },
    }
    return stripe.Event.construct_from(payload, "sk_test_unused_api_key")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_checkout_session_completed_credits_user(client, test_user):
    """
    Full pipeline: real StripeObject -> handler -> credit_balance bumped.

    Verifies both:
      1. The handler returns 200 (not 500 from .get() AttributeError).
      2. The user's credit_balance increased by the metadata.credits value.
    """
    event = _build_checkout_session_completed_event(user_id=test_user, credits=10)

    # Mock construct_event to return our real StripeObject. This bypasses
    # signature verification (we'd need to actually sign the payload),
    # but the object that flows into the handler is the SAME TYPE the
    # production code sees from Stripe — that's what catches the bug class.
    with patch.object(stripe.Webhook, "construct_event", return_value=event):
        resp = client.post(
            "/webhook/stripe",
            data=b"raw_payload_irrelevant_construct_event_is_mocked",
            headers={"Stripe-Signature": "t=0,v1=irrelevant"},
            **HTTPS,
        )

    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}. Body: {resp.data!r}. "
        "If this is AttributeError-related, the StripeObject->dict "
        "conversion at dispatch was likely removed (H6 regression)."
    )
    body = json.loads(resp.data)
    assert body["status"] == "ok"
    assert body.get("credits_added") == 10

    with app.app.app_context():
        u = db.session.get(User, test_user)
        assert u.credit_balance == 20, (
            f"Expected 20 (10 starting + 10 from Starter pack), got {u.credit_balance}"
        )


def test_checkout_session_completed_is_idempotent(client, test_user):
    """
    Stripe retries webhooks on 5xx. The handler is guarded by
    UNIQUE(stripe_tx_id) on Transaction. A second delivery of the same
    event MUST NOT double-credit the user.
    """
    event = _build_checkout_session_completed_event(user_id=test_user, credits=10)

    with patch.object(stripe.Webhook, "construct_event", return_value=event):
        first = client.post(
            "/webhook/stripe",
            data=b"x",
            headers={"Stripe-Signature": "t=0,v1=x"},
            **HTTPS,
        )
        second = client.post(
            "/webhook/stripe",
            data=b"x",
            headers={"Stripe-Signature": "t=0,v1=x"},
            **HTTPS,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    # Second delivery should report duplicate, not double-credit.
    second_body = json.loads(second.data)
    assert second_body.get("duplicate") is True or second_body.get("status") == "ok"

    with app.app.app_context():
        u = db.session.get(User, test_user)
        assert u.credit_balance == 20, (
            f"Idempotency broken: balance should be 20 after replay, got {u.credit_balance}"
        )


def test_subscription_deleted_flips_status(client, test_user):
    """
    A user with an active subscription gets their status flipped to
    'canceled' when Stripe fires customer.subscription.deleted.

    The handler at app.py:2459 looks up the user by subscription_id —
    so we have to wire that linkage up first.
    """
    sub_id = "sub_test_for_cancel"
    with app.app.app_context():
        u = db.session.get(User, test_user)
        u.subscription_id = sub_id
        u.subscription_status = "active"
        u.cancel_at_period_end = True
        db.session.commit()

    event = _build_subscription_deleted_event(sub_id=sub_id)

    with patch.object(stripe.Webhook, "construct_event", return_value=event):
        resp = client.post(
            "/webhook/stripe",
            data=b"x",
            headers={"Stripe-Signature": "t=0,v1=x"},
            **HTTPS,
        )

    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}. Body: {resp.data!r}"
    )

    with app.app.app_context():
        u = db.session.get(User, test_user)
        assert u.subscription_status == "canceled"
        assert u.cancel_at_period_end is False


# ---------------------------------------------------------------------------
# The bug-class regression test — the whole reason this file exists
# ---------------------------------------------------------------------------


def test_real_stripeobject_does_not_break_handler(client, test_user):
    """
    Regression guard for Hotfix-6 Additions 4 + 5.

    If anyone reintroduces .get() access on the raw event or event_obj
    before the to_dict_recursive() conversion, this test will fail with
    AttributeError surfaced as a 500. With the conversion in place, the
    handler should accept a real StripeObject and process it cleanly.

    This is the test that would have caught the H6 bug before deploy.
    """
    event = _build_checkout_session_completed_event(user_id=test_user)

    # Pre-flight sanity: confirm we're actually feeding a StripeObject,
    # not a dict. If this assertion fails, the test is no longer guarding
    # the bug class — fix the test, don't suppress the assertion. The
    # "StripeObject" base class lives under stripe._stripe_object across
    # SDK 2.x — that path is private but stable; if it moves again,
    # update the import and add a comment for the next reader.
    from stripe._stripe_object import StripeObject
    assert isinstance(event, StripeObject), (
        "Test fixture must be a real StripeObject to guard against the "
        "H6 bug class. Got: " + type(event).__name__
    )
    # The actual failure mode: StripeObject does NOT expose .get() as
    # a method — so hasattr(event, "get") is False, and event.get("id")
    # raises AttributeError via __getattr__. If this changes (the SDK
    # adds .get()), the original bug is gone and this guard becomes
    # documentation only; relax to a soft warning then.
    assert not hasattr(event, "get"), (
        "StripeObject now exposes .get() — the H6 bug class is no "
        "longer reachable. Convert this assertion to a comment."
    )

    with patch.object(stripe.Webhook, "construct_event", return_value=event):
        resp = client.post(
            "/webhook/stripe",
            data=b"x",
            headers={"Stripe-Signature": "t=0,v1=x"},
            **HTTPS,
        )

    # The whole point: must not 500 with AttributeError.
    assert resp.status_code == 200, (
        f"Handler returned {resp.status_code} on a real StripeObject. "
        "If response body mentions AttributeError or 'get', the "
        "StripeObject->dict conversion at app.py dispatch was removed. "
        f"Body: {resp.data!r}"
    )


# ---------------------------------------------------------------------------
# Signature verification still gates traffic
# ---------------------------------------------------------------------------


def test_invalid_signature_returns_400(client, test_user):
    """
    When construct_event raises SignatureVerificationError (real path,
    not mocked), the route must 400 — not 500. Tests the except branch
    at app.py around line 2535.
    """
    with patch.object(
        stripe.Webhook,
        "construct_event",
        side_effect=stripe.error.SignatureVerificationError("bad signature", "sig"),
    ):
        resp = client.post(
            "/webhook/stripe",
            data=b"x",
            headers={"Stripe-Signature": "t=0,v1=bad"},
            **HTTPS,
        )
    assert resp.status_code == 400


def test_missing_webhook_secret_returns_503(client, monkeypatch, test_user):
    """
    If config.STRIPE_WEBHOOK_SECRET is unset, the route refuses to even
    attempt verification — fails closed at 503.
    """
    monkeypatch.setattr(app.config, "STRIPE_WEBHOOK_SECRET", None)
    resp = client.post(
        "/webhook/stripe",
        data=b"x",
        headers={"Stripe-Signature": "t=0,v1=x"},
        **HTTPS,
    )
    assert resp.status_code == 503
