import unittest
import json
from decimal import Decimal
from engine import calculate_quote

PROFILE_ID = "Residential_Standard"


def _job(panes, add_ons=None):
    """Helper: build a job_data dict that targets the test profile."""
    return {
        "panes": panes,
        "add_ons": add_ons or [],
        "profile_id": PROFILE_ID,
        "overrides": {},
        "addon_overrides": {},
        "tax_override": None,
    }


class TestQuotingEngine(unittest.TestCase):
    def setUp(self):
        # Sprint 2 engine API: price data lives under a named profile in a
        # registry. Tests wrap their Decimal price sheet accordingly.
        self.price_registry = {
            "profiles": {
                PROFILE_ID: {
                    "base_pane_rate": Decimal('5.00'),
                    "base_callout_fee": Decimal('75.00'),
                    "tax_rate": Decimal('0.10'),  # 10% for easier math
                    "story_surcharges": {
                        "floor1": Decimal('1.0'),
                        "floor2": Decimal('1.2'),
                        "floor3": Decimal('1.4'),
                    },
                    "add_on_rates": {
                        "Screen Cleaning": Decimal('2.00'),
                        "Track Cleaning": Decimal('3.00'),
                        "Hard Water Treatment": Decimal('5.00'),
                    },
                },
            },
            "active_profile": PROFILE_ID,
        }

    def test_minimum_callout_fee(self):
        # Low pane count (2 panes on floor 1 = $10)
        # Should be bumped to $75 callout fee + tax
        result = calculate_quote(_job({"floor1": 2}), self.price_registry)

        # Base: max(75, 10) = 75. Tax: 7.50. Total: 82.50
        self.assertEqual(result['calculation']['final_before_tax'], Decimal('75.00'))
        self.assertEqual(result['calculation']['grand_total'], Decimal('82.50'))

    def test_multi_story_calculation(self):
        # Floor 1: 10 * 5 * 1.0 = 50
        # Floor 2: 5 * 5 * 1.2 = 30
        # Total: 80. (Above 75 callout)
        # Tax: 8.00. Total: 88.00
        result = calculate_quote(_job({"floor1": 10, "floor2": 5}), self.price_registry)

        self.assertEqual(result['calculation']['subtotal_panes'], Decimal('80.00'))
        self.assertEqual(result['calculation']['grand_total'], Decimal('88.00'))

    def test_add_ons_per_pane(self):
        # Floor 1: 10 * 5 * 1.0 = 50
        # Add-on 'Screen Cleaning': 10 panes * 2.00 = 20
        # Total: 70. (Below 75 callout)
        # Max(75, 70) = 75. Tax: 7.50. Total: 82.50
        result = calculate_quote(
            _job({"floor1": 10}, ["Screen Cleaning"]),
            self.price_registry,
        )

        self.assertEqual(result['calculation']['subtotal_addons'], Decimal('20.00'))
        self.assertEqual(result['calculation']['final_before_tax'], Decimal('75.00'))

    def test_negative_pane_count(self):
        # Input validation for negative panes
        with self.assertRaises(ValueError):
            calculate_quote(_job({"floor1": -5}), self.price_registry)

    def test_zero_pane_count(self):
        # 0 panes should just result in the callout fee + tax
        result = calculate_quote(_job({}), self.price_registry)
        self.assertEqual(result['calculation']['final_before_tax'], Decimal('75.00'))

    def test_snapshot_integrity(self):
        # Ensure the result contains all necessary data for a frozen record
        result = calculate_quote(_job({"floor1": 20}), self.price_registry)

        self.assertIn("timestamp", result)
        self.assertIn("pricing_applied", result)
        self.assertEqual(result['pricing_applied']['base_pane_rate'], Decimal('5.00'))

if __name__ == "__main__":
    unittest.main()
