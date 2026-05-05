"""
Sprint 3 (pipeline) tests — distinct from legacy test_sprint3.py which
covers pre-pipeline Sprint 3 work (Quote persistence, IDOR, Decimal,
benchmark, engine purity). This file covers the new pipeline Sprint 3:
rate limiting, free tier expansion, contact intake, account security.

Helper tests (pure functions) live alongside Flask-bound integration tests
(via _fresh_app); the integration tests follow the pattern established in
the legacy test_sprint3.py.
"""

import os
import sys
import tempfile
import importlib
import unittest
from datetime import datetime, timedelta
from decimal import Decimal

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


def _fresh_app():
    """Boot a fresh app against a temp sqlite DB so tests don't pollute sovereign.db."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["SRE_SECRET_KEY"] = "test"
    os.environ.pop("STRIPE_SECRET_KEY", None)
    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

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


def _register_and_login(app_mod, client, email, password="pw1234567", verify=True):
    """
    Register + auto-login the user, then by default flip email_verified=True
    so /generate works. Tests that specifically need to exercise the
    verification gate (T4) pass verify=False and assert the 403.
    Password defaults to a string satisfying T4's strength rules.
    """
    client.post("/register", data={"email": email, "password": password}, follow_redirects=True)
    client.post("/login", data={"email": email, "password": password}, follow_redirects=True)
    if verify:
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email=email).first()
            if user:
                user.email_verified = True
                user.email_verification_token = None
                user.email_verification_token_expires = None
                app_mod.db.session.commit()


def _seed_quotes(app_mod, user_id, count, base_time=None):
    """
    Insert `count` Quote rows for user_id with created_at spread across the
    last 60 minutes. Bypasses /generate entirely so the rate limit logic
    sees a populated history without recursing through itself.
    """
    base_time = base_time or datetime.utcnow()
    with app_mod.app.app_context():
        for i in range(count):
            q = app_mod.Quote(
                user_id=user_id,
                label=f"seed-{i}",
                final_price=Decimal("100.00"),
                pane_count=1,
                quote_data={"input": {"panes": {"floor1": 1}},
                            "calculation": {"grand_total": "100.00"}},
                # Distribute oldest at -55min, newest at -10min, so they all
                # fall within the rolling 60-min window.
                created_at=base_time - timedelta(minutes=55 - (i * 4)),
            )
            app_mod.db.session.add(q)
        app_mod.db.session.commit()


# ---------- Pure helper tests ----------

class TestRateLimitNoticeHelper(unittest.TestCase):
    """T1 — pure-function rate-limit decision + countdown formatting."""

    def setUp(self):
        from notices import build_rate_limit_notice
        self.build = build_rate_limit_notice
        self.now = datetime(2026, 5, 3, 12, 0, 0)
        self.threshold = 10

    def test_below_threshold_returns_none(self):
        oldest = self.now - timedelta(minutes=30)
        self.assertIsNone(self.build(9, self.threshold, oldest, self.now))

    def test_at_threshold_returns_notice(self):
        oldest = self.now - timedelta(minutes=50)  # falls out in 10 min
        notice = self.build(10, self.threshold, oldest, self.now)
        self.assertIsNotNone(notice)
        self.assertEqual(notice["code"], "RATE_LIMITED")
        self.assertEqual(notice["retry_after_minutes"], 10)
        self.assertIn("Next available in 10 minutes", notice["message"])
        self.assertIn("10 quotes this hour", notice["message"])

    def test_singular_minute_grammar(self):
        oldest = self.now - timedelta(minutes=59, seconds=30)  # ~30s left
        notice = self.build(10, self.threshold, oldest, self.now)
        self.assertEqual(notice["retry_after_minutes"], 1)
        self.assertIn("1 minute.", notice["message"])
        self.assertNotIn("1 minutes", notice["message"])

    def test_countdown_rounds_up(self):
        # 65 seconds left -> rounds up to 2 minutes (don't undersell the wait).
        oldest = self.now - timedelta(minutes=58, seconds=55)
        notice = self.build(10, self.threshold, oldest, self.now)
        self.assertEqual(notice["retry_after_minutes"], 2)

    def test_well_above_threshold_still_uses_oldest(self):
        # Even with 100 quotes piled up, the wait keys off the OLDEST one
        # falling out — that's when the rolling count drops below threshold.
        oldest = self.now - timedelta(minutes=20)
        notice = self.build(100, self.threshold, oldest, self.now)
        self.assertEqual(notice["retry_after_minutes"], 40)


# ---------- Integration tests (Flask test client) ----------

class TestRateLimitIntegration(unittest.TestCase):
    """T1 — wired-up behavior on /generate."""

    def test_free_user_eleventh_request_returns_429(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "ratelimit@test.com")

        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="ratelimit@test.com").first()
            user_id = user.id

        # Pre-seed the rate-limit window so the next /generate is the 11th.
        _seed_quotes(app_mod, user_id, count=10)

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "11th",
        })
        self.assertEqual(r.status_code, 429, r.data)
        body = r.get_json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["code"], "RATE_LIMITED")
        self.assertIn("Next available in", body["message"])
        self.assertIn("retry_after_minutes", body)

        # Credits must not have been touched — rate limit fires before reserve.
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="ratelimit@test.com").first()
            self.assertEqual(user.credit_balance, 10)  # STARTING_CREDITS post-T2

    def test_subscriber_bypasses_rate_limit(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "sub@test.com")

        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="sub@test.com").first()
            user.subscription_status = "active"
            user.subscription_id = "sub_test_xyz"
            user.subscription_current_period_end = datetime.utcnow() + timedelta(days=90)
            app_mod.db.session.commit()
            user_id = user.id

        # Seed 15 quotes — well above the 10-per-hour limit.
        _seed_quotes(app_mod, user_id, count=15)

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "16th",
        })
        # Subscriber bypass — rate limit must not fire. Whatever happens
        # next (success / unrelated failure), it's not 429.
        self.assertNotEqual(r.status_code, 429,
                            f"subscriber blocked by rate limit: {r.data}")

    def test_past_due_subscriber_is_rate_limited(self):
        # past_due is NOT exempt — they fall through to credits and the
        # rate limit. An account in dunning shouldn't double as a firehose.
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "pd@test.com")

        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="pd@test.com").first()
            user.subscription_status = "past_due"
            user.subscription_id = "sub_pd_xyz"
            user.subscription_current_period_end = datetime.utcnow() + timedelta(days=10)
            app_mod.db.session.commit()
            user_id = user.id

        _seed_quotes(app_mod, user_id, count=10)

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "pd-11th",
        })
        self.assertEqual(r.status_code, 429, r.data)


class TestFreeTierExpansion(unittest.TestCase):
    """T2 — STARTING_CREDITS bumped to 10, one-time floor migration, NO_CREDITS prompt."""

    def test_starting_credits_constant(self):
        import config
        self.assertEqual(config.STARTING_CREDITS, 10)

    def test_new_user_starts_with_ten_credits(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "newbie@test.com")
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="newbie@test.com").first()
            self.assertEqual(user.credit_balance, 10)

    def test_no_credits_returns_402_with_pricing_hint(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "broke@test.com")

        # Drain credits directly so the next /generate hits the reserve floor.
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="broke@test.com").first()
            user.credit_balance = 0
            app_mod.db.session.commit()

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "no-credits",
        })
        self.assertEqual(r.status_code, 402, r.data)
        body = r.get_json()
        self.assertEqual(body["code"], "NO_CREDITS")
        self.assertIn("$8.99", body["message"])
        self.assertIn("Annual Unlimited", body["message"])
        self.assertEqual(body["redirect"], "/top-up")

    def test_starting_credit_floor_bumps_users_below_threshold(self):
        app_mod, _ = _fresh_app()
        # Direct DB inserts (bypass the registration route — its session
        # logic complicates multi-user setup in a single test client).
        with app_mod.app.app_context():
            for email, balance in [("a@test.com", 5), ("b@test.com", 3),
                                   ("c@test.com", 10)]:
                u = app_mod.User(email=email, credit_balance=balance)
                u.set_password("pw12345")
                app_mod.db.session.add(u)
            app_mod.db.session.commit()

            app_mod._ensure_starting_credit_floor()

            self.assertEqual(
                app_mod.User.query.filter_by(email="a@test.com").first().credit_balance, 10)
            self.assertEqual(
                app_mod.User.query.filter_by(email="b@test.com").first().credit_balance, 10)
            self.assertEqual(
                app_mod.User.query.filter_by(email="c@test.com").first().credit_balance, 10)

    def test_floor_migration_doesnt_lower_already_above(self):
        # If a user has 50 credits (purchased a pack), the floor migration
        # must NOT clamp them down to STARTING_CREDITS.
        app_mod, _ = _fresh_app()
        with app_mod.app.app_context():
            u = app_mod.User(email="rich@test.com", credit_balance=50)
            u.set_password("pw12345")
            app_mod.db.session.add(u)
            app_mod.db.session.commit()

            app_mod._ensure_starting_credit_floor()

            user = app_mod.User.query.filter_by(email="rich@test.com").first()
            self.assertEqual(user.credit_balance, 50)


class TestContactIntake(unittest.TestCase):
    """T3 — /contact form: validation, persistence, soft-cap CTA wiring."""

    def test_get_renders_form(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "lead@test.com")
        r = client.get("/contact")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode("utf-8")
        self.assertIn("Custom plan inquiry", body)
        self.assertIn('name="company_name"', body)
        self.assertIn('name="current_volume"', body)
        self.assertIn('name="expected_growth"', body)
        self.assertIn('name="email"', body)

    def test_missing_fields_rejected(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "lead@test.com")
        r = client.post("/contact", data={
            "company_name": "Acme",
            "current_volume": "",
            "expected_growth": "2x",
            "email": "lead@test.com",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Required: Current quote volume", r.data)
        with app_mod.app.app_context():
            self.assertEqual(app_mod.ContactSubmission.query.count(), 0)

    def test_invalid_email_rejected(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "lead@test.com")
        r = client.post("/contact", data={
            "company_name": "Acme", "current_volume": "100/wk",
            "expected_growth": "2x", "email": "not-an-email",
        }, follow_redirects=True)
        self.assertIn(b"valid email", r.data)
        with app_mod.app.app_context():
            self.assertEqual(app_mod.ContactSubmission.query.count(), 0)

    def test_valid_submission_persists_and_flashes_success(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "lead@test.com")
        r = client.post("/contact", data={
            "company_name": "Acme Window Co",
            "current_volume": "~80/week, seasonal",
            "expected_growth": "2x next year",
            "email": "billing@acme.com",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"we&#39;ll be in touch", r.data)

        with app_mod.app.app_context():
            sub = app_mod.ContactSubmission.query.first()
            self.assertIsNotNone(sub)
            self.assertEqual(sub.company_name, "Acme Window Co")
            self.assertEqual(sub.current_volume, "~80/week, seasonal")
            self.assertEqual(sub.expected_growth, "2x next year")
            # Email lowercased on intake (matches login/register normalization).
            self.assertEqual(sub.email, "billing@acme.com")
            user = app_mod.User.query.filter_by(email="lead@test.com").first()
            self.assertEqual(sub.user_id, user.id)

    def test_unauthenticated_redirected_to_login(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        r = client.get("/contact")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_soft_cap_cta_points_at_contact_route(self):
        # Round-trip: notices.build_soft_cap_notice + app.py's /generate
        # call site agree on /contact as the CTA target.
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "sub2@test.com")
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="sub2@test.com").first()
            user.subscription_status = "active"
            user.subscription_id = "sub_cta_test"
            user.subscription_current_period_end = datetime.utcnow() + timedelta(days=90)
            app_mod.db.session.commit()
            user_id = user.id

        # Pre-seed enough quotes to trip the soft cap.
        with app_mod.app.app_context():
            base = datetime.utcnow()
            for i in range(app_mod.config.SOFT_CAP_THRESHOLD):
                q = app_mod.Quote(
                    user_id=user_id, label=f"sc-{i}",
                    final_price=Decimal("1.00"), pane_count=1,
                    quote_data={"input": {}, "calculation": {"grand_total": "1"}},
                    created_at=base - timedelta(days=1),
                )
                app_mod.db.session.add(q)
            app_mod.db.session.commit()

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "softcap-trip",
        })
        self.assertEqual(r.status_code, 200, r.data)
        body = r.get_json()
        self.assertIn("soft_cap_notice", body)
        self.assertEqual(body["soft_cap_notice"]["contact_url"], "/contact")


class TestPasswordStrengthHelper(unittest.TestCase):
    """T4 — pure-function password strength check."""

    def setUp(self):
        # Imported here so failures during T4 wire-up surface as test failures
        # rather than collection errors before the rest of the suite runs.
        from app import _password_strength_error
        self.check = _password_strength_error

    def test_too_short_rejected(self):
        self.assertIn("8 characters", self.check("abc1"))

    def test_no_digit_rejected(self):
        self.assertIn("number", self.check("abcdefghij"))

    def test_strong_password_accepted(self):
        self.assertIsNone(self.check("password1"))
        self.assertIsNone(self.check("Tr0ub4dor"))


class TestRegistrationPasswordRules(unittest.TestCase):
    """T4 — /register enforces password strength."""

    def test_weak_password_rejected_no_user_created(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        r = client.post("/register", data={
            "email": "weak@test.com", "password": "abc",
        }, follow_redirects=True)
        self.assertIn(b"8 characters", r.data)
        with app_mod.app.app_context():
            self.assertIsNone(
                app_mod.User.query.filter_by(email="weak@test.com").first()
            )

    def test_no_digit_password_rejected(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        r = client.post("/register", data={
            "email": "nodigit@test.com", "password": "abcdefghij",
        }, follow_redirects=True)
        self.assertIn(b"number", r.data)
        with app_mod.app.app_context():
            self.assertIsNone(
                app_mod.User.query.filter_by(email="nodigit@test.com").first()
            )


class TestLoginLockout(unittest.TestCase):
    """T4 — 5 failed logins → 15-min cooldown."""

    def _seed_user(self, app_mod, email, password="goodpass1"):
        with app_mod.app.app_context():
            u = app_mod.User(email=email)
            u.set_password(password)
            u.email_verified = True
            app_mod.db.session.add(u)
            app_mod.db.session.commit()
            return u.id

    def test_five_failures_locks_account(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        self._seed_user(app_mod, "lock@test.com")

        # 5 wrong-password attempts.
        for i in range(5):
            client.post("/login", data={
                "email": "lock@test.com", "password": "wrongpass99",
            }, follow_redirects=True)

        with app_mod.app.app_context():
            u = app_mod.User.query.filter_by(email="lock@test.com").first()
            self.assertIsNotNone(u.locked_until)
            self.assertGreater(u.locked_until, datetime.utcnow())
            # Counter resets to 0 once consumed into a lockout.
            self.assertEqual(u.failed_login_attempts, 0)

        # 6th attempt with the CORRECT password is rejected during cooldown.
        r = client.post("/login", data={
            "email": "lock@test.com", "password": "goodpass1",
        }, follow_redirects=True)
        self.assertIn(b"temporarily locked", r.data)

    def test_successful_login_resets_counter(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        self._seed_user(app_mod, "reset@test.com")

        # 3 wrong attempts (under the 5 threshold).
        for _ in range(3):
            client.post("/login", data={
                "email": "reset@test.com", "password": "badpass99",
            }, follow_redirects=True)

        with app_mod.app.app_context():
            u = app_mod.User.query.filter_by(email="reset@test.com").first()
            self.assertEqual(u.failed_login_attempts, 3)

        # Now log in correctly — counter and lockout should reset.
        client.post("/login", data={
            "email": "reset@test.com", "password": "goodpass1",
        }, follow_redirects=True)

        with app_mod.app.app_context():
            u = app_mod.User.query.filter_by(email="reset@test.com").first()
            self.assertEqual(u.failed_login_attempts, 0)
            self.assertIsNone(u.locked_until)


class TestEmailVerificationGate(unittest.TestCase):
    """T4 — /generate blocks unverified users; /verify/<token> unblocks."""

    def test_unverified_user_blocked_from_generate(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        # verify=False: leave email_verified at False after register/login.
        _register_and_login(app_mod, client, "unv@test.com", verify=False)

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "blocked",
        })
        self.assertEqual(r.status_code, 403, r.data)
        body = r.get_json()
        self.assertEqual(body["code"], "EMAIL_NOT_VERIFIED")

    def test_verify_endpoint_clears_token_and_flips_flag(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "ver@test.com", verify=False)

        # Grab the token that registration generated.
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="ver@test.com").first()
            token = user.email_verification_token
            self.assertIsNotNone(token)
            self.assertFalse(user.email_verified)

        r = client.get(f"/verify/{token}", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="ver@test.com").first()
            self.assertTrue(user.email_verified)
            self.assertIsNone(user.email_verification_token)
            self.assertIsNone(user.email_verification_token_expires)

    def test_invalid_verification_token_rejected(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        r = client.get("/verify/garbage-token-does-not-exist", follow_redirects=True)
        self.assertIn(b"invalid or has already been used", r.data)

    def test_expired_verification_token_rejected(self):
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "expired@test.com", verify=False)

        # Backdate the token expiry so it's already stale.
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="expired@test.com").first()
            user.email_verification_token_expires = datetime.utcnow() - timedelta(hours=1)
            token = user.email_verification_token
            app_mod.db.session.commit()

        r = client.get(f"/verify/{token}", follow_redirects=True)
        self.assertIn(b"expired", r.data)
        with app_mod.app.app_context():
            user = app_mod.User.query.filter_by(email="expired@test.com").first()
            self.assertFalse(user.email_verified)

    def test_subscriber_also_must_verify(self):
        # Subscribers are NOT exempt — stolen-card subscriptions would
        # otherwise bypass the gate. Pre-execution decision.
        app_mod, _ = _fresh_app()
        client = app_mod.app.test_client()
        _register_and_login(app_mod, client, "subuv@test.com", verify=False)
        with app_mod.app.app_context():
            u = app_mod.User.query.filter_by(email="subuv@test.com").first()
            u.subscription_status = "active"
            u.subscription_id = "sub_unv_test"
            u.subscription_current_period_end = datetime.utcnow() + timedelta(days=90)
            app_mod.db.session.commit()

        r = client.post("/generate", json={
            "panes": {"floor1": 1, "floor2": 0, "floor3": 0},
            "add_ons": [], "profile_id": None, "overrides": {},
            "addon_overrides": {}, "tax_override": None, "label": "sub-blocked",
        })
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["code"], "EMAIL_NOT_VERIFIED")


class TestEmailVerifiedBackfill(unittest.TestCase):
    """T4 — pre-Sprint-3 users grandfathered as verified."""

    def test_backfill_only_touches_users_without_token(self):
        app_mod, _ = _fresh_app()
        with app_mod.app.app_context():
            # User A: no token (pre-Sprint-3 shape).
            a = app_mod.User(email="legacy@test.com", email_verified=False)
            a.set_password("legacypass1")
            # User B: has a token (Sprint-3-registered, hasn't verified).
            b = app_mod.User(
                email="newuser@test.com", email_verified=False,
                email_verification_token="ABCDEF1234567890",
                email_verification_token_expires=datetime.utcnow() + timedelta(hours=24),
            )
            b.set_password("newpass1234")
            app_mod.db.session.add_all([a, b])
            app_mod.db.session.commit()

            app_mod._backfill_email_verified()

            a = app_mod.User.query.filter_by(email="legacy@test.com").first()
            b = app_mod.User.query.filter_by(email="newuser@test.com").first()
            self.assertTrue(a.email_verified, "pre-Sprint-3 user should be grandfathered")
            self.assertFalse(b.email_verified, "Sprint-3 user with pending token must NOT be auto-verified")


if __name__ == "__main__":
    unittest.main()
