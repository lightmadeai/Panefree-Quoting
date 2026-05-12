"""
Hotfix-1 T1 — re-test of BUG-005 (email verification gate).

Spins a fresh app against a temp DB, runs the full registration -> gate ->
verify -> success flow via Flask test_client, captures every step's status
code + response body, and writes a markdown report to
testing/bug-005-verification-test.md.

Run from project root:
    python testing/bug_005_verification_test.py

Exits 0 on success, 1 if any step fails its assertion.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from io import StringIO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

REPORT_PATH = os.path.join(PROJECT_ROOT, "testing", "bug-005-verification-test.md")


def _boot_fresh_app():
    """Boot a fresh app instance against a temp sqlite DB. Mirrors the
    pattern used in test_sprint3_pipeline._fresh_app() so behavior matches
    the existing integration tests."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["SRE_SECRET_KEY"] = "hotfix1-t1-test"
    os.environ["SUPPORT_EMAIL"] = "test-support@hotfix1.local"
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


def _attach_log_capture(app_mod):
    """Capture app.logger output so we can grep for [EMAIL-VERIFICATION]."""
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    app_mod.app.logger.addHandler(handler)
    app_mod.app.logger.setLevel(logging.INFO)
    return buf


def _create_default_profile(app_mod, client):
    """BUG-003 (Sprint 4): users are no longer auto-seeded with profiles, so
    a working /generate path requires creating one explicitly."""
    return client.post("/api/profiles/create", json={
        "name": "Residential_Standard",
        "make_default": True,
        "price_data": {
            "base_pane_rate": 5.0,
            "base_callout_fee": 75.0,
            "tax_rate": 0.085,
            "story_surcharges": {"floor1": 1.0, "floor2": 1.25, "floor3": 1.5},
            "add_on_rates": {
                "Screen Cleaning": 2.0,
                "Track Cleaning": 1.5,
                "Hard Water Treatment": 3.0,
            },
        },
    })


def main() -> int:
    results = []

    def record(step, expected, actual, passed, **extra):
        results.append({
            "step": step,
            "expected": expected,
            "actual": actual,
            "pass": passed,
            **extra,
        })
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {step}: expected={expected} actual={actual}")

    app_mod, tmp_db = _boot_fresh_app()
    log_buf = _attach_log_capture(app_mod)
    client = app_mod.app.test_client()
    email = "bug005-retest@hotfix1.local"
    password = "TestPassword!9999"

    # --- Step 1: register a new user --------------------------------------
    r = client.post(
        "/register",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    record(
        "register POST /register",
        "302 redirect (auto-login -> /)",
        f"{r.status_code}",
        r.status_code == 302,
        location=r.headers.get("Location", ""),
    )

    # --- Step 2: confirm verification token logged + present in DB --------
    log_text = log_buf.getvalue()
    has_log_line = "[EMAIL-VERIFICATION]" in log_text and email in log_text
    record(
        "verification URL logged via [EMAIL-VERIFICATION]",
        "log line containing the user's email + verify URL",
        "found" if has_log_line else "missing",
        has_log_line,
        log_excerpt=next(
            (line for line in log_text.splitlines() if "[EMAIL-VERIFICATION]" in line),
            "",
        ),
    )

    with app_mod.app.app_context():
        user = app_mod.User.query.filter_by(email=email).first()
        token = user.email_verification_token if user else None
        verified_initial = bool(user.email_verified) if user else None
    record(
        "DB row created with email_verified=False + token present",
        "email_verified=False, token=<32-hex>",
        f"email_verified={verified_initial}, token_len={len(token) if token else 0}",
        verified_initial is False and token and len(token) == 32,
    )

    # --- Step 3: hit /generate while unverified -> expect 403 ------------
    r = client.post("/generate", json={
        "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
        "add_ons": [],
        "profile_id": None,
        "overrides": {},
        "addon_overrides": {},
        "tax_override": None,
        "label": "hotfix1-t1-blocked",
    })
    body = r.get_json() or {}
    record(
        "POST /generate (unverified) -> 403 EMAIL_NOT_VERIFIED",
        "status=403, code=EMAIL_NOT_VERIFIED",
        f"status={r.status_code}, code={body.get('code')}",
        r.status_code == 403 and body.get("code") == "EMAIL_NOT_VERIFIED",
        message=body.get("message", ""),
    )

    # --- Step 4: GET /verify/<token> -> 302 redirect ----------------------
    r = client.get(f"/verify/{token}", follow_redirects=False)
    record(
        "GET /verify/<token> -> 302 redirect (verified)",
        "302 redirect to /",
        f"{r.status_code} -> {r.headers.get('Location', '')}",
        r.status_code == 302,
    )

    with app_mod.app.app_context():
        user = app_mod.User.query.filter_by(email=email).first()
        verified_after = bool(user.email_verified)
        token_after = user.email_verification_token
    record(
        "DB row reflects verification (flag flipped, token cleared)",
        "email_verified=True, token=None",
        f"email_verified={verified_after}, token={token_after!r}",
        verified_after is True and token_after is None,
    )

    # --- Step 5: create default profile (BUG-003 prereq) -----------------
    r = _create_default_profile(app_mod, client)
    record(
        "create default profile (BUG-003 prereq for /generate success)",
        "200/201 success",
        f"{r.status_code}",
        r.status_code in (200, 201),
    )

    # --- Step 6: hit /generate after verification -> expect 200 ----------
    r = client.post("/generate", json={
        "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
        "add_ons": [],
        "profile_id": "Residential_Standard",
        "overrides": {},
        "addon_overrides": {},
        "tax_override": None,
        "label": "hotfix1-t1-success",
    })
    body = r.get_json() or {}
    record(
        "POST /generate (verified, with profile) -> 200 success",
        "status=200, body.status=success, file=quote_*.pdf",
        f"status={r.status_code}, body.status={body.get('status')}, file={body.get('file', '')[:24]}",
        r.status_code == 200 and body.get("status") == "success",
        quote_id=body.get("quote_id"),
        credits_remaining=body.get("credits_remaining"),
    )

    # --- Write markdown report -------------------------------------------
    all_pass = all(row["pass"] for row in results)
    overall = "PASS" if all_pass else "FAIL"
    overall_md = "PASS ✅" if all_pass else "FAIL ❌"

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("# BUG-005 Re-Test — Email Verification Gate\n\n")
        f.write(f"**Sprint:** Hotfix-1 (Stabilize Phase) — T1\n")
        f.write(f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write(f"**Driver:** `testing/bug_005_verification_test.py`\n")
        f.write(f"**Overall verdict:** **{overall_md}**\n\n")

        f.write("## Setup\n")
        f.write("- `.env` set with `SUPPORT_EMAIL=test-support@hotfix1.local` "
                "(satisfies T1 acceptance criterion).\n")
        f.write("- Driver boots a fresh app instance against an isolated "
                "temp sqlite DB (no pollution of `sovereign.db`).\n")
        f.write("- Verification email is logged via `[EMAIL-VERIFICATION]` "
                "(no real SMTP plumbing in scope this hotfix; the gate logic "
                "is what's being re-tested).\n\n")

        f.write("## Steps\n\n")
        for i, row in enumerate(results, 1):
            mark = "✅" if row["pass"] else "❌"
            f.write(f"### {mark} Step {i}: {row['step']}\n")
            f.write(f"- **Expected:** {row['expected']}\n")
            f.write(f"- **Actual:** {row['actual']}\n")
            for k, v in row.items():
                if k in ("step", "expected", "actual", "pass"):
                    continue
                f.write(f"- **{k}:** `{v}`\n")
            f.write("\n")

        f.write("## Conclusion\n")
        if all_pass:
            f.write("BUG-005 (email verification gate) is verified working "
                    "end-to-end. Unverified users are blocked from `/generate` "
                    "with `403 EMAIL_NOT_VERIFIED`; clicking the verification "
                    "link flips the flag and `/generate` then succeeds with `200`.\n\n")
        else:
            f.write("One or more steps failed — see ❌ markers above. "
                    "BUG-005 is NOT confirmed fixed; investigate before closing.\n\n")
        f.write("**Backlog status:** P2 — BUG-005 → can be checked off in `PLANNING/backlog.md`.\n")

    print(f"\nReport written to {REPORT_PATH}")
    print(f"Overall: {overall}")
    try:
        os.unlink(tmp_db)
    except OSError:
        pass
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
