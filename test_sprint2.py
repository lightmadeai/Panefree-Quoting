"""
Sprint 2 unit tests — pricing constants, cancel-at-period-end UX, soft-cap CTA.

Each test maps to one acceptance criterion in PLANNING/done/sprint-2.md (or
current-sprint.md while sprint is in flight). Pure-Python tests where
possible; Flask-dependent tests use a minimal app context fixture.
"""

import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, StrictUndefined

import config

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _jinja_env():
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), undefined=StrictUndefined)
    env.globals["url_for"] = lambda endpoint, **kw: f"/{endpoint}"
    env.globals["get_flashed_messages"] = lambda **kw: []
    return env


def _fake_user(**kw):
    """Minimal stand-in for a logged-in User row, sufficient for template rendering."""
    base = dict(
        email="t@x.com", credit_balance=10,
        business_name=None, phone_number=None,
        quote_footer_text=None, invoice_footer_text=None,
        invoice_prefix="INV-", next_invoice_number=1,
        subscription_status=None, subscription_id=None,
        subscription_current_period_end=None,
        cancel_at_period_end=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestPricingConstants(unittest.TestCase):
    """T1 acceptance — config values match Chris's revised tier table."""

    def test_starter_pack(self):
        self.assertEqual(config.CREDIT_PACKS["starter"]["price_cents"], 899)
        self.assertEqual(config.CREDIT_PACKS["starter"]["credits"], 10)

    def test_pro_pack(self):
        self.assertEqual(config.CREDIT_PACKS["pro"]["price_cents"], 3900)
        self.assertEqual(config.CREDIT_PACKS["pro"]["credits"], 50)

    def test_studio_pack(self):
        self.assertEqual(config.CREDIT_PACKS["studio"]["price_cents"], 6900)
        self.assertEqual(config.CREDIT_PACKS["studio"]["credits"], 100)

    def test_annual_subscription(self):
        self.assertEqual(config.ANNUAL_SUBSCRIPTION["price_cents"], 17900)
        self.assertEqual(config.ANNUAL_SUBSCRIPTION["interval"], "year")

    def test_soft_cap_default(self):
        # Default when SOFT_CAP_THRESHOLD env is unset — covered when the
        # test runs without the env var set to a custom value.
        import os
        if "SOFT_CAP_THRESHOLD" in os.environ:
            self.skipTest("SOFT_CAP_THRESHOLD env override active")
        self.assertEqual(config.SOFT_CAP_THRESHOLD, 1000)


class TestCancelAtPeriodEndUX(unittest.TestCase):
    """T2 acceptance — UI swaps "Renews on" for "Cancels on" when flag set."""

    def setUp(self):
        self.env = _jinja_env()
        self.account_tpl = self.env.get_template("account.html")
        self.nav_tpl = self.env.get_template("_nav.html")
        self.account_ctx = dict(
            default_quote_footer="DQF", default_invoice_footer="DIF",
            invoice_prefix_default="INV-", invoice_prefix_input_max=16,
        )
        self.future = datetime.utcnow() + timedelta(days=90)

    def test_renewing_subscriber_sees_renews(self):
        user = _fake_user(
            subscription_status="active", subscription_id="sub_X",
            subscription_current_period_end=self.future,
            cancel_at_period_end=False,
        )
        html = self.account_tpl.render(current_user=user, **self.account_ctx)
        self.assertIn("Renews on:", html)
        self.assertNotIn("Cancels on:", html)

    def test_cancel_pending_subscriber_sees_cancels(self):
        user = _fake_user(
            subscription_status="active", subscription_id="sub_X",
            subscription_current_period_end=self.future,
            cancel_at_period_end=True,
        )
        html = self.account_tpl.render(current_user=user, **self.account_ctx)
        self.assertIn("Cancels on:", html)
        self.assertNotIn("Renews on:", html)

    def test_nav_badge_swaps_verb(self):
        renewing = _fake_user(
            subscription_status="active",
            subscription_current_period_end=self.future,
            cancel_at_period_end=False,
        )
        canceling = _fake_user(
            subscription_status="active",
            subscription_current_period_end=self.future,
            cancel_at_period_end=True,
        )
        renewing_html = self.nav_tpl.render(current_user=renewing)
        canceling_html = self.nav_tpl.render(current_user=canceling)
        self.assertIn("renews", renewing_html)
        self.assertNotIn("cancels", renewing_html)
        self.assertIn("cancels", canceling_html)
        self.assertNotIn("renews", canceling_html)
        # Nav still announces "Unlimited" during cancel-pending — paid access
        # continues through period_end regardless of the cancel schedule.
        self.assertIn("Unlimited", canceling_html)


class TestPricingPageGrid(unittest.TestCase):
    """T4 acceptance — 4-tier grid renders for all relevant user states."""

    def setUp(self):
        self.env = _jinja_env()
        self.tpl = self.env.get_template("top_up.html")
        self.ctx_real_stripe = dict(
            credit_packs=config.CREDIT_PACKS,
            annual=config.ANNUAL_SUBSCRIPTION,
            soft_cap=config.SOFT_CAP_THRESHOLD,
            publishable_key="pk_test_xxx",
            simulator_active=False,
        )
        self.ctx_simulator = dict(self.ctx_real_stripe,
                                  publishable_key=None, simulator_active=True)

    def test_non_subscriber_sees_all_four_tiers(self):
        user = _fake_user()
        html = self.tpl.render(current_user=user, **self.ctx_real_stripe)
        self.assertIn("Starter", html)
        self.assertIn("Pro", html)
        self.assertIn("Studio", html)
        self.assertIn("Annual Unlimited", html)
        # Discount math comes from configured prices, not hardcoded strings.
        self.assertIn("13% off Starter", html)
        self.assertIn("23% off Starter", html)
        self.assertIn("97%+ off Starter", html)
        # Annual price + soft cap surfaced.
        self.assertIn("$179", html)
        self.assertIn("1,000", html)

    def test_active_subscriber_sees_banner_not_grid(self):
        user = _fake_user(
            subscription_status="active",
            subscription_id="sub_X",
            subscription_current_period_end=datetime.utcnow() + timedelta(days=90),
        )
        html = self.tpl.render(current_user=user, **self.ctx_real_stripe)
        self.assertIn("Annual Unlimited Active", html)
        self.assertIn("Manage subscription", html)
        # Grid suppressed — Buy Credits / Subscribe buttons should be absent.
        self.assertNotIn("Buy Credits", html)
        self.assertNotIn(">Subscribe<", html)

    def test_past_due_subscriber_sees_reactivate_cta(self):
        user = _fake_user(
            subscription_status="past_due",
            subscription_id="sub_X",
            subscription_current_period_end=datetime.utcnow() + timedelta(days=10),
        )
        html = self.tpl.render(current_user=user, **self.ctx_real_stripe)
        # Past-due users still see the 4-tier grid (they need the credit
        # path as a stopgap), but the Annual card is highlighted.
        self.assertIn("Your plan — past due", html)
        self.assertIn("Reactivate", html)
        self.assertIn("Buy Credits", html)

    def test_simulator_disables_subscribe_only(self):
        user = _fake_user()
        html = self.tpl.render(current_user=user, **self.ctx_simulator)
        # Credit packs simulate-clickable; Annual disabled with explanation.
        self.assertIn("🧪 Simulate Starter", html)
        self.assertIn("Subscribe (sim N/A)", html)


class TestSoftCapCTA(unittest.TestCase):
    """
    Sprint 2 T3 acceptance — soft-cap CTA payload shape.
    Sprint 3 T3 changed `contact_email` to `contact_url` (now points at the
    in-app /contact form instead of mailto:). Tests updated accordingly.
    """

    def setUp(self):
        from notices import build_soft_cap_notice
        self.build = build_soft_cap_notice
        self.threshold = 1000
        self.url = "/contact"

    def test_below_threshold_returns_none(self):
        self.assertIsNone(self.build(999, self.threshold, self.url))

    def test_at_threshold_returns_cta(self):
        notice = self.build(1000, self.threshold, self.url)
        self.assertIsNotNone(notice)
        self.assertEqual(notice["count"], 1000)
        self.assertEqual(notice["threshold"], 1000)
        self.assertIn("1000 of 1000", notice["message"])
        self.assertIn("custom pricing", notice["message"])
        self.assertEqual(notice["contact_url"], "/contact")
        # Sprint 3 dropped contact_email — caller passes the URL it wants.
        self.assertNotIn("contact_email", notice)

    def test_above_threshold_returns_cta(self):
        notice = self.build(2500, self.threshold, self.url)
        self.assertIsNotNone(notice)
        self.assertEqual(notice["count"], 2500)
        self.assertIn("2500 of 1000", notice["message"])

    def test_threshold_zero_means_always_show(self):
        # Edge case: threshold=0 with any count >=0 returns a notice.
        # Not a configuration we'd ship, but the function shouldn't trip on it.
        self.assertIsNotNone(self.build(0, 0, self.url))

    def test_caller_chooses_url_shape(self):
        # Helper is URL-agnostic — caller can pass mailto:, https://, /path, etc.
        for url in ["mailto:x@y.com", "https://example.com/contact", "/contact"]:
            notice = self.build(1000, self.threshold, url)
            self.assertEqual(notice["contact_url"], url)


if __name__ == "__main__":
    unittest.main()
