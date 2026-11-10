# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestContractCandidateSelection(TransactionCase):
    """Contract price and eligibility use the same source in both channels."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parent = cls.env["res.partner"].create({"name": "Blanket company"})
        cls.other = cls.env["res.partner"].create({"name": "Unrelated buyer"})
        cls.product = cls.env["product.product"].create({
            "name": "Test contracted item", "sale_ok": True, "list_price": 17.0,
        })
        cls.pricelist = cls.parent.property_product_pricelist
        today = fields.Date.today()
        cls.agreement = cls.env["sale.blanket.order"].create({
            "partner_id": cls.parent.id,
            "pricelist_id": cls.pricelist.id,
            "validity_start_date": today - timedelta(days=1),
            "validity_date": today + timedelta(days=30),
            "line_ids": [Command.create({
                "product_id": cls.product.id,
                "original_uom_qty": 1000,
                "product_uom": cls.product.uom_id.id,
                "price_unit": 8.00,
            })],
        })
        cls.agreement.action_confirm()

    def test_contract_is_customer_specific(self):
        model = self.env["sale.blanket.order.line"]
        allowed = model._tl_website_candidates(
            self.product, self.parent, self.env.company, self.agreement.currency_id
        )
        denied = model._tl_website_candidates(
            self.product, self.other, self.env.company, self.agreement.currency_id
        )
        self.assertIn(self.agreement.line_ids, allowed)
        self.assertFalse(denied)

    def test_contract_price_and_available_quantity(self):
        line = self.agreement.line_ids
        self.assertEqual(line._tl_price_for_uom(self.product.uom_id), 8.00)
        self.assertTrue(line._tl_available_for_sale_line(200, self.product.uom_id))
        self.assertFalse(line._tl_available_for_sale_line(1001, self.product.uom_id))
