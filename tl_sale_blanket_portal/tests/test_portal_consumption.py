# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from types import SimpleNamespace

from odoo.tests.common import TransactionCase

from ..controllers.main import line_consumption, status_domain


class TestPortalConsumption(TransactionCase):
    def test_status_filters_distinguish_cancelled_from_expired(self):
        self.assertIn(("tl_portal_cancelled", "=", True), status_domain("cancelled"))
        self.assertIn(("tl_portal_cancelled", "=", False), status_domain("expired"))
        self.assertEqual(status_domain("all"), [])
        # Malformed input cannot erase the default open-only filter.
        self.assertEqual(status_domain("invalid"), status_domain("open"))

    def test_confirmed_percentage_excludes_unconfirmed_cart(self):
        product = object()

        class Uom:
            @staticmethod
            def _compute_quantity(quantity, other):
                return quantity

        uom = Uom()

        def sale_line(quantity, state):
            return SimpleNamespace(
                product_id=product,
                product_uom_id=uom,
                product_uom_qty=quantity,
                order_id=SimpleNamespace(state=state),
            )

        line = SimpleNamespace(
            product_id=product,
            product_uom=uom,
            original_uom_qty=100,
            sale_lines=[sale_line(20, "sale"), sale_line(15, "draft"),
                        sale_line(7, "cancel"), sale_line(10, "sent")],
        )
        values = line_consumption(line, precision_digits=2)
        self.assertEqual(values["consumed"], 20)
        self.assertEqual(values["draft"], 25)
        self.assertEqual(values["percentage"], 20)
        self.assertEqual(values["percentage_display"], "20.0%")

    def test_zero_contract_qty_cannot_divide_by_zero(self):
        product = object()
        line = SimpleNamespace(product_id=product, product_uom=None,
                               original_uom_qty=0, sale_lines=[])
        self.assertEqual(line_consumption(line)["percentage"], 0)
