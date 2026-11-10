# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from ..models.product_template import _tl_contract_availability_rows


@tagged("post_install", "-at_install")
class TestWebsiteContractAvailability(TransactionCase):
    def test_no_balance_for_empty_contract_recordset(self):
        self.assertEqual(
            _tl_contract_availability_rows(self.env["sale.blanket.order.line"], "es_ES"),
            [],
        )

    def test_only_eligible_customer_gets_available_contract_quantity(self):
        buyer = self.env["res.partner"].create({"name": "Customer A"})
        outsider = self.env["res.partner"].create({"name": "Customer B"})
        product = self.env["product.product"].create({
            "name": "Product covered by contract", "sale_ok": True,
        })
        pricelist = buyer.property_product_pricelist
        today = fields.Date.today()
        contract = self.env["sale.blanket.order"].create({
            "partner_id": buyer.id,
            "pricelist_id": pricelist.id,
            "validity_start_date": today - timedelta(days=1),
            "validity_date": today + timedelta(days=30),
            "line_ids": [Command.create({
                "product_id": product.id,
                "original_uom_qty": 1000,
                "product_uom": product.uom_id.id,
                "price_unit": 8.0,
            })],
        })
        contract.action_confirm()
        model = self.env["sale.blanket.order.line"]
        allowed = model._tl_website_candidates(
            product, buyer, self.env.company, contract.currency_id,
        )
        denied = model._tl_website_candidates(
            product, outsider, self.env.company, contract.currency_id,
        )
        balances = _tl_contract_availability_rows(allowed, "es_ES")
        self.assertEqual(len(balances), 1)
        self.assertEqual(balances[0]["contract_name"], contract.name)
        self.assertAlmostEqual(balances[0]["quantity"], 1000.0)
        self.assertEqual(balances[0]["uom_name"], product.uom_id.name)
        self.assertEqual(_tl_contract_availability_rows(denied, "es_ES"), [])
