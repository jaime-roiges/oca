# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestKeptCacheOdoo20(TransactionCase):
    def test_new_line_keeps_cached_price_and_zero(self):
        line = self.env["account.move.line"].new({"price_unit": 12.50})
        self.assertEqual(line._kept_value("price_unit"), 12.50)
        line.price_unit = 0.0
        self.assertEqual(line._kept_value("price_unit"), 0.0)

    def test_new_line_without_cached_value_does_not_query_database(self):
        line = self.env["account.move.line"].new({})
        field = line._fields["price_unit"]
        field._get_cache(line.env).pop(line._ids[0], None)
        self.assertIsNone(line._kept_value("price_unit"))
