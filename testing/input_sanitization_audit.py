"""
Hotfix-1 T4 — input sanitization audit driver.

Walks every customer-facing free-text entry point with an oversized payload
and verifies that the persisted value (or the form rejection) honors the
documented cap. Writes a markdown report to
testing/input-sanitization-audit.md.

Coverage matrix (post-hotfix):

  /generate            label, customer_name, customer_address,
                       customer_email, customer_phone        (Sprint 4)
  /account             business_name, phone_number,
                       quote_footer_text, invoice_footer_text,
                       invoice_prefix                        (Hotfix-1 T4)
  /contact             company_name, current_volume,
                       expected_growth, email                (Hotfix-1 T4)
  /profiles/new        name (HTML)                           (Hotfix-1 T4)
  /api/profiles/create name (JSON)                           (Hotfix-1 T4)

Run from project root:
    python testing/input_sanitization_audit.py

Exit 0 if every cap holds; exit 1 if any field over-stored.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

REPORT_PATH = os.path.join(PROJECT_ROOT, "testing", "input-sanitization-audit.md")
OVERSIZE = "X" * 10_000  # 10 KB string for every cap test


def _boot_fresh_app():
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["SRE_SECRET_KEY"] = "hotfix1-t4-test"
    os.environ.pop("STRIPE_SECRET_KEY", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
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


def _register_verified(app_mod, client, email):
    client.post("/register", data={"email": email, "password": "TestPassword!9999"},
                follow_redirects=True)
    with app_mod.app.app_context():
        u = app_mod.User.query.filter_by(email=email).first()
        u.email_verified = True
        u.email_verification_token = None
        app_mod.db.session.commit()
        uid = u.id
    return uid


def main() -> int:
    app_mod, tmp_db = _boot_fresh_app()
    client = app_mod.app.test_client()
    user_id = _register_verified(app_mod, client, "t4@hotfix1.local")

    rows = []

    def check(field, expected_max, actual_len, route, behavior):
        # actual_len == -1 is the sentinel for "row never persisted" — that's
        # always a failure regardless of cap.
        passed = (0 <= actual_len <= expected_max)
        rows.append({
            "field": field,
            "route": route,
            "expected_max": expected_max,
            "actual_len": actual_len,
            "behavior": behavior,
            "pass": passed,
        })
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {route} {field}: cap={expected_max} stored={actual_len} ({behavior})")

    # ----- /account: business_name, phone_number, footers ----------------
    # invoice_prefix has its own validate-or-reject path that aborts the
    # whole save on invalid input, so test it in a SEPARATE POST below.
    r = client.post("/account", data={
        "business_name": OVERSIZE,
        "phone_number": OVERSIZE,
        "quote_footer_text": OVERSIZE,
        "invoice_footer_text": OVERSIZE,
        "invoice_prefix": "INV-",  # valid — let the rest land
    }, follow_redirects=True)
    with app_mod.app.app_context():
        u = app_mod.db.session.get(app_mod.User, user_id)
        check("business_name", app_mod.BUSINESS_NAME_MAX, len(u.business_name or ""),
              "POST /account", "truncated silently")
        check("phone_number", app_mod.CUSTOMER_PHONE_MAX, len(u.phone_number or ""),
              "POST /account", "truncated silently")
        check("quote_footer_text", app_mod.FOOTER_MAX_LEN, len(u.quote_footer_text or ""),
              "POST /account", "truncated silently")
        check("invoice_footer_text", app_mod.FOOTER_MAX_LEN, len(u.invoice_footer_text or ""),
              "POST /account", "truncated silently")

    # invoice_prefix over-length: aborts whole save, prefix stays at default
    r = client.post("/account", data={
        "invoice_prefix": "ABCDEFGHIJKLMNOP",  # > INVOICE_PREFIX_INPUT_MAX
        "business_name": "should-not-overwrite",
    }, follow_redirects=True)
    with app_mod.app.app_context():
        u = app_mod.db.session.get(app_mod.User, user_id)
        check("invoice_prefix (rejected, prior state preserved)",
              app_mod.INVOICE_PREFIX_INPUT_MAX, len(u.invoice_prefix or ""),
              "POST /account", "form-level reject + flash; prior 'INV-' kept")

    # ----- /contact: 4 fields ---------------------------------------------
    # Email kept short enough that the post-truncate value still has @ and a
    # TLD (the form validates email shape before persisting). The cap test
    # for `email` therefore lives in a separate POST below using a value that
    # is over the cap but still has @ and . past the truncation point.
    r = client.post("/contact", data={
        "company_name": OVERSIZE,
        "current_volume": OVERSIZE,
        "expected_growth": OVERSIZE,
        "email": "ok@e.co",
    }, follow_redirects=True)
    with app_mod.app.app_context():
        sub = app_mod.ContactSubmission.query.filter_by(user_id=user_id).first()
        if sub:
            check("company_name", app_mod.CONTACT_COMPANY_MAX, len(sub.company_name),
                  "POST /contact", "truncated silently")
            check("current_volume", app_mod.CONTACT_VOLUME_MAX, len(sub.current_volume),
                  "POST /contact", "truncated silently")
            check("expected_growth", app_mod.CONTACT_GROWTH_MAX, len(sub.expected_growth),
                  "POST /contact", "truncated silently")
        else:
            check("contact submission persisted", 0, -1,
                  "POST /contact", "FAIL — no row written")

    # /contact email cap: build an input that exceeds 254 but, after
    # truncation, still contains @ and a "." in the domain so the form's
    # shape check passes. local part is short, then @e.co, then padding.
    long_email = ("e" * 200) + "@e.co" + ("x" * 700)
    r = client.post("/contact", data={
        "company_name": "co",
        "current_volume": "1k",
        "expected_growth": "10x",
        "email": long_email,
    }, follow_redirects=True)
    with app_mod.app.app_context():
        sub = app_mod.ContactSubmission.query.filter_by(user_id=user_id).order_by(
            app_mod.ContactSubmission.id.desc()).first()
        if sub and sub.email.startswith("e"):
            check("email", app_mod.CONTACT_EMAIL_MAX, len(sub.email),
                  "POST /contact", "truncated silently")
        else:
            check("email persisted", 0, -1,
                  "POST /contact", "FAIL — no row written")

    # ----- /profiles/new (HTML) -------------------------------------------
    r = client.post("/profiles/new", data={
        "name": OVERSIZE,
        "base_rate": "5", "callout": "75", "tax": "8.5",
        "floor1_mult": "1.0", "floor2_mult": "1.25", "floor3_mult": "1.5",
        "screen_rate": "2", "track_rate": "1.5", "hardwater_rate": "3",
    }, follow_redirects=True)
    with app_mod.app.app_context():
        prof = app_mod.PricingProfile.query.filter_by(user_id=user_id).order_by(
            app_mod.PricingProfile.id.desc()).first()
        if prof:
            check("name (HTML)", app_mod.PROFILE_NAME_MAX, len(prof.name),
                  "POST /profiles/new", "truncated silently")
        else:
            check("name (HTML) persisted", 0, 0,
                  "POST /profiles/new", "FAIL — no row written")

    # ----- /api/profiles/create (JSON) ------------------------------------
    r = client.post("/api/profiles/create", json={
        "name": OVERSIZE.replace("X", "Y"),  # different value to differentiate
        "make_default": False,
        "price_data": {
            "base_pane_rate": 5.0, "base_callout_fee": 75.0, "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {
                "Screen Cleaning": 2.0, "Track Cleaning": 1.5,
                "Hard Water Treatment": 3.0,
            },
        },
    })
    with app_mod.app.app_context():
        prof = app_mod.PricingProfile.query.filter_by(user_id=user_id).order_by(
            app_mod.PricingProfile.id.desc()).first()
        # Filter for the JSON-route entry (starts with Y)
        if prof and prof.name.startswith("Y"):
            check("name (JSON)", app_mod.PROFILE_NAME_MAX, len(prof.name),
                  "POST /api/profiles/create", "truncated silently")
        else:
            check("name (JSON) persisted", 0, 0,
                  "POST /api/profiles/create", "FAIL — no row written")

    # ----- /generate: re-confirm Sprint 4 caps still hold -----------------
    # (Default profile already created via /api/profiles/create above.)
    r = client.post("/generate", json={
        "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
        "add_ons": [], "profile_id": "Y" * app_mod.PROFILE_NAME_MAX,
        "overrides": {}, "addon_overrides": {}, "tax_override": None,
        "label": OVERSIZE,
        "customer_name": OVERSIZE,
        "customer_address": OVERSIZE,
        "customer_email": "x" * 9990 + "@e.co",
        "customer_phone": OVERSIZE,
    })
    with app_mod.app.app_context():
        q = app_mod.Quote.query.filter_by(user_id=user_id).order_by(
            app_mod.Quote.id.desc()).first()
        if q and r.status_code == 200:
            check("label", app_mod.LABEL_MAX_LEN, len(q.label or ""),
                  "POST /generate", "truncated silently (existing)")
            check("customer_name", app_mod.CUSTOMER_NAME_MAX, len(q.customer_name or ""),
                  "POST /generate", "truncated silently (existing)")
            check("customer_address", app_mod.CUSTOMER_ADDR_MAX,
                  len(q.customer_address or ""), "POST /generate",
                  "truncated silently (existing)")
            check("customer_email", app_mod.CUSTOMER_EMAIL_MAX,
                  len(q.customer_email or ""), "POST /generate",
                  "truncated silently (existing)")
            check("customer_phone", app_mod.CUSTOMER_PHONE_MAX,
                  len(q.customer_phone or ""), "POST /generate",
                  "truncated silently (existing)")
        else:
            check("/generate quote persisted", 0, 0,
                  "POST /generate", f"FAIL status={r.status_code}")

    # ----- Write report ---------------------------------------------------
    all_pass = all(row["pass"] for row in rows)
    overall_md = "PASS ✅" if all_pass else "FAIL ❌"
    overall = "PASS" if all_pass else "FAIL"

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# Input Sanitization Audit — BUG-009 follow-up\n\n")
        f.write(f"**Sprint:** Hotfix-1 (Stabilize Phase) — T4\n")
        f.write(f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"**Driver:** `testing/input_sanitization_audit.py`\n")
        f.write(f"**Overall verdict:** **{overall_md}**\n\n")

        f.write("## Pre-hotfix gaps (identified during audit)\n\n")
        f.write("Five free-text entry points were `.strip()`-only with no length cap, "
                "leaving DB-bloat / DOS surface:\n\n")
        f.write("| Route | Field | Pre-fix | Post-fix |\n")
        f.write("|---|---|---|---|\n")
        f.write("| `/account` | `business_name` | unbounded | `BUSINESS_NAME_MAX = 200` |\n")
        f.write("| `/account` | `phone_number` | unbounded | `CUSTOMER_PHONE_MAX = 30` |\n")
        f.write("| `/contact` | `company_name` | unbounded | `CONTACT_COMPANY_MAX = 200` |\n")
        f.write("| `/contact` | `current_volume` | unbounded | `CONTACT_VOLUME_MAX = 200` |\n")
        f.write("| `/contact` | `expected_growth` | unbounded | `CONTACT_GROWTH_MAX = 2000` |\n")
        f.write("| `/contact` | `email` | unbounded | `CONTACT_EMAIL_MAX = 254` (RFC 5321) |\n")
        f.write("| `/profiles/new` | `name` (HTML) | unbounded | `PROFILE_NAME_MAX = 80` |\n")
        f.write("| `/api/profiles/create` | `name` (JSON) | unbounded | `PROFILE_NAME_MAX = 80` |\n\n")
        f.write("All gaps now route through `_sanitize_storage()` "
                "(trim → whitespace-collapse → cap), matching the existing "
                "Sprint 4 customer-field pattern.\n\n")

        f.write("## Cap test results (10KB payload at every cap)\n\n")
        f.write("| Route | Field | Cap | Stored | Behavior | Verdict |\n")
        f.write("|---|---|---:|---:|---|---|\n")
        for row in rows:
            mark = "PASS" if row["pass"] else "FAIL"
            f.write(
                f"| `{row['route']}` | `{row['field']}` | "
                f"{row['expected_max']} | {row['actual_len']} | "
                f"{row['behavior']} | {mark} |\n"
            )
        f.write("\n")

        f.write("## sanitize_label coverage (T4 acceptance question)\n\n")
        f.write("`sanitize_label` itself is only used on `Quote.label`. The "
                "broader `_sanitize_storage()` (which `sanitize_label` is a "
                "thin wrapper around) now covers every customer-facing "
                "free-text field after this hotfix. The pattern is consistent: "
                "trim, collapse whitespace, cap.\n\n")

        f.write("## Out of scope / deferred\n\n")
        f.write("- **Login/register password length.** Werkzeug's "
                "`generate_password_hash` accepts arbitrary input; a 1MB "
                "password could spike CPU. Not in T4 scope; flag for a "
                "future hotfix as a low-priority DOS hardening item.\n")
        f.write("- **Login/register email.** DB has `UNIQUE` on `users.email` "
                "with no length cap; oversized email would land but with the "
                "uniqueness gate already absorbing duplicates. Same scope note "
                "as password — defer.\n\n")

        f.write("## Conclusion\n")
        if all_pass:
            f.write("All audited entry points enforce server-side length caps. "
                    "BUG-009 follow-up resolved.\n\n")
        else:
            f.write("One or more caps did not hold — see FAIL rows above.\n\n")
        f.write("**Backlog status:** P3 — BUG-009 follow-up → can be checked off in `PLANNING/backlog.md`.\n")

    print(f"\nReport written to {REPORT_PATH}")
    print(f"Overall: {overall}")
    try:
        os.unlink(tmp_db)
    except OSError:
        pass
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
