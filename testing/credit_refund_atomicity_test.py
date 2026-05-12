"""
Hotfix-1 T5 — credit refund atomicity (OBS-002).

Two scenarios:

  1. Happy path: /generate fails inside the render block. The except
     handler refunds the credit and the user ends up with the same
     balance they had before the call.

  2. Refund-failure path: the rollback succeeds but the refund UPDATE
     itself raises (simulated DB lock / disk error). Pre-hotfix this
     would have propagated as a 500 — the user would lose a credit AND
     get an opaque error. Post-hotfix the refund failure is caught,
     logged loudly with [CREDIT-REFUND-FAILED], and the response is
     the original 400 with the engine error.

Run from project root:
    python testing/credit_refund_atomicity_test.py
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import tempfile
from io import StringIO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _boot():
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["SRE_SECRET_KEY"] = "hotfix1-t5-test"
    os.environ.pop("STRIPE_SECRET_KEY", None)
    import config
    config.DATABASE_PATH = tmp_db
    config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_db}"
    importlib.reload(config)
    import app as app_mod
    importlib.reload(app_mod)
    app_mod.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_db}"
    app_mod.app.config["TESTING"] = True
    app_mod.app.config["WTF_CSRF_ENABLED"] = False
    with app_mod.app.app_context():
        app_mod.db.drop_all()
        app_mod.db.create_all()
    return app_mod, tmp_db


def _verified_user_with_profile(app_mod, client, email):
    client.post("/register", data={"email": email, "password": "TestPassword!9999"},
                follow_redirects=True)
    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email=email).first()
        u.email_verified = True
        u.email_verification_token = None
        app_mod.db.session.commit()
        uid = u.id
        starting = u.credit_balance
    client.post("/api/profiles/create", json={
        "name": "Default", "make_default": True,
        "price_data": {
            "base_pane_rate": 5.0, "base_callout_fee": 75.0, "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {
                "Screen Cleaning": 2.0, "Track Cleaning": 1.5,
                "Hard Water Treatment": 3.0,
            },
        },
    })
    return uid, starting


def _attach_log_capture(app_mod):
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.ERROR)
    handler.setFormatter(logging.Formatter("%(message)s"))
    app_mod.app.logger.addHandler(handler)
    app_mod.app.logger.setLevel(logging.ERROR)
    return buf


GOOD_PAYLOAD = {
    "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
    "add_ons": [], "profile_id": "Default",
    "overrides": {}, "addon_overrides": {}, "tax_override": None,
    "label": "t5",
}


def scenario_happy_refund(app_mod, client, uid, starting):
    """Force the engine to raise; expect 400 + credit refunded."""
    import app as app_module
    original = app_module.calculate_quote

    def boom(*a, **kw):
        raise RuntimeError("simulated render failure")
    app_module.calculate_quote = boom
    try:
        r = client.post("/generate", json=GOOD_PAYLOAD)
    finally:
        app_module.calculate_quote = original

    with app_mod.app.app_context():
        u = app_mod.db.session.get(app_mod.User, uid)
        balance = u.credit_balance

    passed = r.status_code == 400 and balance == starting
    print(f"[{'PASS' if passed else 'FAIL'}] happy refund: "
          f"status={r.status_code} (want 400), balance={balance} "
          f"(want {starting})")
    return passed


def scenario_refund_failure(app_mod, client, uid, log_buf):
    """Force calculate_quote to fail AND the refund UPDATE to fail.
    Pre-hotfix: 500. Post-hotfix: 400 + [CREDIT-REFUND-FAILED] in the log."""
    import app as app_module
    original_calc = app_module.calculate_quote
    original_execute = app_mod.db.session.execute

    def boom_calc(*a, **kw):
        raise RuntimeError("simulated render failure")

    refund_attempts = {"count": 0}

    def selective_execute(stmt, *a, **kw):
        # Only sabotage the refund UPDATE, not the reserve / other queries.
        text_str = str(stmt)
        if "credit_balance + 1" in text_str:
            refund_attempts["count"] += 1
            raise RuntimeError("simulated DB lock during refund")
        return original_execute(stmt, *a, **kw)

    log_buf.seek(0); log_buf.truncate()  # reset capture for this scenario

    app_module.calculate_quote = boom_calc
    # Patch the bound session.execute on the module-level db
    app_mod.db.session.execute = selective_execute  # type: ignore[assignment]
    try:
        r = client.post("/generate", json=GOOD_PAYLOAD)
    finally:
        app_module.calculate_quote = original_calc
        app_mod.db.session.execute = original_execute  # restore

    log_text = log_buf.getvalue()
    has_log = "[CREDIT-REFUND-FAILED]" in log_text
    no_500 = r.status_code == 400
    refund_was_attempted = refund_attempts["count"] >= 1

    passed = has_log and no_500 and refund_was_attempted
    print(f"[{'PASS' if passed else 'FAIL'}] refund-failure path: "
          f"status={r.status_code} (want 400 not 500), "
          f"refund_attempts={refund_attempts['count']} (want >=1), "
          f"log_has_CREDIT-REFUND-FAILED={has_log}")
    if not passed:
        print(f"  log capture: {log_text!r}")
    return passed


def main():
    app_mod, tmp_db = _boot()
    log_buf = _attach_log_capture(app_mod)
    client = app_mod.app.test_client()
    uid, starting = _verified_user_with_profile(app_mod, client, "t5@hotfix1.local")

    ok1 = scenario_happy_refund(app_mod, client, uid, starting)
    # After scenario 1, balance should be back to `starting`. Re-fetch.
    with app_mod.app.app_context():
        starting2 = app_mod.db.session.get(app_mod.User, uid).credit_balance
    ok2 = scenario_refund_failure(app_mod, client, uid, log_buf)

    overall = ok1 and ok2
    print(f"\nOverall: {'PASS' if overall else 'FAIL'}")
    try:
        os.unlink(tmp_db)
    except OSError:
        pass
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
