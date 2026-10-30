# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Standalone tests: cumulative BC3 certification and idempotency keys."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.bc3_parser import Bc3Error, parse_bc3  # noqa: E402
from lib.import_logic import budget_key, certification_period, validate_budget_keys  # noqa: E402


class TestBc3ImportLogic(unittest.TestCase):
    def test_certification_is_incremental_and_repeat_is_zero(self):
        self.assertEqual(certification_period(70, 40, 100), 30)
        self.assertEqual(certification_period(70, 70, 100), 0)
        self.assertEqual(certification_period(70, 80 - 10, 100), 0)
        self.assertEqual(certification_period(1, 0.5, 1), 0.5)

    def test_economic_coefficient_origin_and_increment(self):
        from lib.import_logic import coefficient_origin_ratio
        origin = coefficient_origin_ratio(700, 1000)
        self.assertAlmostEqual(origin, 0.7)
        # A contractual GG row of qty=1 is certified as a *ratio*, so a
        # previous origin of 0.4 means the period is 0.3 of the 130 EUR GG.
        self.assertAlmostEqual(certification_period(origin, 0.4, 1), 0.3)
        self.assertAlmostEqual(certification_period(origin, 0.7, 1), 0)
        self.assertEqual(coefficient_origin_ratio(0, 1000), 0)
        with self.assertRaises(Bc3Error):
            coefficient_origin_ratio(1050, 1000)
        with self.assertRaises(Bc3Error):
            coefficient_origin_ratio(100, 0)

    def test_negative_or_over_contract_origin_is_rejected(self):
        for args in [(110, 40, 100), (20, 40, 100), (-1, 0, 100)]:
            with self.subTest(args=args), self.assertRaises(Bc3Error):
                certification_period(*args)

    def test_tree_keys_prevent_duplicate_ambiguous_codes(self):
        source = "\n".join([
            "~C|ROOT##||Root||||", "~C|X|u|Item|10|||",
            "~D|ROOT##|X\\1\\1\\X\\1\\1\\|",
        ])
        lines = parse_bc3(source).iter_budget_lines()
        self.assertEqual(validate_budget_keys(lines), ["1", "2"])
        self.assertEqual([line.code for line in lines], ["X", "X"])
        self.assertEqual(budget_key(("2", "1", "3")), "2.1.3")
        with self.assertRaises(Bc3Error):
            validate_budget_keys([SimpleNamespace(position=("1",)), SimpleNamespace(position=("1",))])


# Standalone safety check for quantities and prices within permitted input
# bounds that would nevertheless overflow once multiplied.
class TestEconomicPreflight(unittest.TestCase):
    def test_budget_total_checks_product_and_sum(self):
        from lib.import_logic import validated_budget_total
        make = lambda code, q, p: SimpleNamespace(kind="item", code=code, quantity=q, price=p)
        self.assertEqual(validated_budget_total([make("A", 3, 20), make("B", 5, 10)]), 110)
        with self.assertRaisesRegex(Bc3Error, "desbordado"):
            validated_budget_total([make("A", 1e17, 1e17)])
        with self.assertRaisesRegex(Bc3Error, "desbordado"):
            validated_budget_total([make("A", 9e17, 1), make("B", 9e17, 1)])


if __name__ == "__main__":
    unittest.main()

