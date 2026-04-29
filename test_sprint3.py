"""
Sprint 3 integration tests.

Covers:
- Quote persistence on /generate
- Invoice conversion is free (no credit decrement)
- Cross-tenant IDOR block on /quotes/<id>/pdf (Heresy #8)
- Lossless Decimal round-trip (Heresy #11)
- Label sanitization (Heresy #10)
- Benchmark gating (Heresy #9: hidden until > 3 quotes)
- Engine-purity: engine.py imports nothing from the app layer.
"""
import os
import sys
import tempfile
import importlib
from decimal import Decimal

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def _fresh_app():
    """Boot a fresh app against a temp sqlite DB so tests don't pollute sovereign.db."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["SRE_SECRET_KEY"] = "test"
    os.environ.pop("STRIPE_SECRET_KEY", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

    # Reload config + app with the temp DB path before importing app.
    import config
    config.DATABASE_PATH = tmp_db
    config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_db}"

    import app as app_mod
    importlib.reload(app_mod)
    app_mod.app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_db}"
    app_mod.app.config["TESTING"] = True
    app_mod.app.config["WTF_CSRF_ENABLED"] = False

    with app_mod.app.app_context():
        app_mod.db.drop_all()
        app_mod.db.create_all()

    return app_mod, tmp_db


def _register_and_login(app_mod, client, email, password="pw12345"):
    client.post("/register", data={"email": email, "password": password}, follow_redirects=True)


def test_engine_purity():
    import engine
    src = open(engine.__file__).read()
    assert "flask" not in src.lower(), "engine.py must not import flask"
    assert "models" not in src, "engine.py must not import models"
    assert "current_user" not in src, "engine.py must be user/DB-agnostic"
    print("OK: engine purity preserved")


def test_label_sanitization():
    app_mod, _ = _fresh_app()
    s = app_mod.sanitize_label
    assert s(None) == ""
    assert s("") == ""
    assert s("   Smith\n\tFamily   ") == "Smith Family"
    assert len(s("x" * 500)) == 80
    print("OK: label sanitization enforces Heresy #10 caps")


def test_quote_persist_and_invoice_is_free():
    app_mod, _ = _fresh_app()
    client = app_mod.app.test_client()
    _register_and_login(app_mod, client, "a@test.com")

    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email="a@test.com").first()
        starting = u.credit_balance

    r = client.post("/generate", json={
        "panes": {"floor1": 10, "floor2": 5, "floor3": 0},
        "add_ons": [],
        "profile_id": None,
        "overrides": {},
        "addon_overrides": {},
        "tax_override": None,
        "label": "Smith Family — North Side\nmore text",
    })
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["status"] == "success"
    quote_id = body["quote_id"]

    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email="a@test.com").first()
        assert u.credit_balance == starting - 1, "quote must charge exactly 1 credit"
        q = app_mod.Quote.query.get(quote_id)
        # DB keeps the full unicode label (em-dash intact); newlines collapsed.
        assert q.label == "Smith Family \u2014 North Side more text"
        assert q.pane_count == 15
        assert Decimal(q.final_price) > 0

    # Invoice conversion — must be FREE.
    r2 = client.post(
        f"/quotes/{quote_id}/pdf?type=INVOICE",
        headers={"Accept": "application/json"},
    )
    assert r2.status_code == 200, r2.data
    body2 = r2.get_json()
    assert body2["status"] == "success"
    assert body2["doc_type"] == "INVOICE"

    with app_mod.app.app_context():
        u2 = app_mod.User.query.filter_by(email="a@test.com").first()
        assert u2.credit_balance == starting - 1, "invoice conversion must NOT charge credits"
    print("OK: quote persisted, invoice conversion is free (Heresy #7 gate holds)")


def test_cross_tenant_idor_blocked():
    app_mod, _ = _fresh_app()
    client_a = app_mod.app.test_client()
    client_b = app_mod.app.test_client()
    _register_and_login(app_mod, client_a, "a@test.com")
    _register_and_login(app_mod, client_b, "b@test.com")

    r = client_a.post("/generate", json={
        "panes": {"floor1": 5, "floor2": 0, "floor3": 0},
        "add_ons": [], "profile_id": None, "overrides": {}, "addon_overrides": {},
        "tax_override": None, "label": "A Co",
    })
    assert r.status_code == 200
    a_quote_id = r.get_json()["quote_id"]

    r2 = client_b.post(
        f"/quotes/{a_quote_id}/pdf?type=INVOICE",
        headers={"Accept": "application/json"},
    )
    assert r2.status_code == 404, f"Heresy #8: cross-tenant access must 404, got {r2.status_code}"
    print("OK: cross-tenant IDOR blocked (Heresy #8)")


def test_lossless_decimal_roundtrip():
    app_mod, _ = _fresh_app()
    client = app_mod.app.test_client()
    _register_and_login(app_mod, client, "c@test.com")
    r = client.post("/generate", json={
        "panes": {"floor1": 7, "floor2": 3, "floor3": 2},
        "add_ons": ["Screen Cleaning"],
        "profile_id": None, "overrides": {}, "addon_overrides": {},
        "tax_override": None, "label": "Decimal test",
    })
    assert r.status_code == 200
    qid = r.get_json()["quote_id"]

    with app_mod.app.app_context():
        q = app_mod.Quote.query.get(qid)
        snap = app_mod.load_quote_snapshot(q)
        gt = snap["calculation"]["grand_total"]
        assert isinstance(gt, Decimal), "rehydrated grand_total must be a Decimal"
        assert str(gt) == str(Decimal(q.final_price)), "round-trip must be exact"
    print("OK: Decimal round-trip is lossless (Heresy #11)")


def test_doc_code_is_stable_across_rerenders():
    """Same stored Quote must yield the same doc code on every re-render."""
    from generator import derive_doc_code
    assert derive_doc_code(1) == derive_doc_code(1)
    assert derive_doc_code(1) != derive_doc_code(2)
    assert len(derive_doc_code(42)) == 8
    assert derive_doc_code(42).isupper() or derive_doc_code(42).isdigit() or all(
        c.isdigit() or c.isupper() for c in derive_doc_code(42)
    )

    app_mod, _ = _fresh_app()
    client = app_mod.app.test_client()
    _register_and_login(app_mod, client, "e@test.com")
    r = client.post("/generate", json={
        "panes": {"floor1": 5, "floor2": 0, "floor3": 0},
        "add_ons": [], "profile_id": None, "overrides": {}, "addon_overrides": {},
        "tax_override": None, "label": "Stable code test",
    })
    assert r.status_code == 200
    qid = r.get_json()["quote_id"]
    expected_code = derive_doc_code(qid)

    # Regenerate twice (once as QUOTE, once as INVOICE) — both should reuse
    # the same 8-char code since they render from the same stored row.
    r1 = client.post(f"/quotes/{qid}/pdf?type=QUOTE", headers={"Accept": "application/json"})
    r2 = client.post(f"/quotes/{qid}/pdf?type=INVOICE", headers={"Accept": "application/json"})
    assert r1.status_code == 200 and r2.status_code == 200

    # Spot-check that the derivation is actually deterministic.
    assert derive_doc_code(qid) == expected_code
    print("OK: doc codes are stable across quote/invoice re-renders")


def test_benchmark_gated_by_history_count():
    app_mod, _ = _fresh_app()
    client = app_mod.app.test_client()
    _register_and_login(app_mod, client, "d@test.com")

    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email="d@test.com").first()

    # 0 quotes → no benchmark
    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email="d@test.com").first()
        assert app_mod.compute_internal_benchmark(u, 10, "100.00") is None

    # Add 3 quotes manually — still at threshold (<=3), should stay hidden.
    for i in range(3):
        client.post("/generate", json={
            "panes": {"floor1": 10, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {}, "addon_overrides": {},
            "tax_override": None, "label": f"q{i}",
        })
    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email="d@test.com").first()
        assert app_mod.compute_internal_benchmark(u, 10, "100.00") is None, \
            "benchmark must stay hidden at n<=3 (Heresy #9)"

    # 4th quote unlocks it.
    client.post("/generate", json={
        "panes": {"floor1": 10, "floor2": 0, "floor3": 0},
        "add_ons": [], "profile_id": None, "overrides": {}, "addon_overrides": {},
        "tax_override": None, "label": "q4",
    })
    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email="d@test.com").first()
        b = app_mod.compute_internal_benchmark(u, 10, "100.00")
        assert b is not None, "benchmark should unlock at n>3"
        assert b["sample_size"] >= 1
    print("OK: benchmark gating enforced (Heresy #9)")


if __name__ == "__main__":
    test_engine_purity()
    test_label_sanitization()
    test_quote_persist_and_invoice_is_free()
    test_cross_tenant_idor_blocked()
    test_lossless_decimal_roundtrip()
    test_doc_code_is_stable_across_rerenders()
    test_benchmark_gated_by_history_count()
    print("\nAll Sprint 3 tests passed.")
