# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Regression scenario for a sale order with two distinct blanket contracts.

To be executed by Odoo 20's test runner; this file has only been compiled
statically in the build environment, never executed against a registry.
"""
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("-at_install", "post_install")
class TestMixedContractOrder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Mixed Contract Customer"})
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Mixed Contract Prices",
            "currency_id": cls.env.company.currency_id.id,
        })
        cls.products = cls.env["product.product"].create([
            {"name": "Custom Glass"},
            {"name": "Custom Napkin"},
            {"name": "Regular Detergent"},
        ])

    def _make_contract(self, product, contracted_qty):
        today = fields.Date.today()
        contract = self.env["sale.blanket.order"].create({
            "partner_id": self.customer.id,
            "company_id": self.env.company.id,
            "pricelist_id": self.pricelist.id,
            "validity_start_date": today - timedelta(days=1),
            "validity_date": today + timedelta(days=90),
            "line_ids": [Command.create({
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "original_uom_qty": contracted_qty,
                "price_unit": 2.0,
            })],
        })
        contract.action_confirm()
        return contract

    def test_one_sale_order_consumes_two_contracts_plus_normal_line(self):
        first, second, normal = self.products
        contract_a = self._make_contract(first, 1000)
        contract_b = self._make_contract(second, 500)
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "company_id": self.env.company.id,
            "pricelist_id": self.pricelist.id,
            "order_line": [
                Command.create({
                    "product_id": first.id,
                    "product_uom_qty": 200,
                    "product_uom_id": first.uom_id.id,
                    "blanket_order_line": contract_a.line_ids.id,
                }),
                Command.create({
                    "product_id": second.id,
                    "product_uom_qty": 300,
                    "product_uom_id": second.uom_id.id,
                    "blanket_order_line": contract_b.line_ids.id,
                }),
                Command.create({
                    "product_id": normal.id,
                    "product_uom_qty": 10,
                    "product_uom_id": normal.uom_id.id,
                }),
            ],
        })
        self.assertEqual(len(order.order_line), 3)
        self.assertEqual(order.order_line[0].blanket_order_line, contract_a.line_ids)
        self.assertEqual(order.order_line[1].blanket_order_line, contract_b.line_ids)
        self.assertFalse(order.order_line[2].blanket_order_line)
        self.assertFalse(order.blanket_order_id)  # Not a single-contract order.
        order.action_confirm()
        self.assertEqual(contract_a.line_ids.remaining_uom_qty, 800)
        self.assertEqual(contract_b.line_ids.remaining_uom_qty, 200)
