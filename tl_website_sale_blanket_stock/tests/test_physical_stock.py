# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWebStockAddon(TransactionCase):
    def test_stock_guard_fields_exist(self):
        line = self.env["sale.blanket.order.line"]
        self.assertIn("tl_dedicated_available_qty", line._fields)
        self.assertIn("tl_dedicated_location_id", line._fields)
        self.assertIn("tl_dedicated_warehouse_id", line._fields)
