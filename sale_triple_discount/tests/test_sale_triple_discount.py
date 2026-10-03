# Copyright 2017 Tecnativa - David Vidal
# Copyright 2018 Simone Rubino - Agile Business Group
# Copyright 2022 Manuel Regidor - Sygel Technology
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.tests import common


class TestSaleTripleDiscount(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref("sale.group_discount_per_so_line")
        cls.partner = cls.env["res.partner"].create({"name": "Triple Discount Buyer"})
        cls.product = cls.env["product.product"].create(
            {"name": "Test Product", "type": "service", "invoice_policy": "order"}
        )
        cls.tax = cls.env["account.tax"].create(
            {
                "name": "TAX 15%",
                "amount_type": "percent",
                "type_tax_use": "sale",
                "amount": 15.0,
            }
        )
        cls.order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.line = cls.env["sale.order.line"].create(
            {
                "order_id": cls.order.id,
                "product_id": cls.product.id,
                "product_uom_qty": 1.0,
                "tax_ids": [Command.set(cls.tax.ids)],
                "price_unit": 600.0,
            }
        )

    def _invoice_line(self):
        self.order.action_confirm()
        self.order._create_invoices()
        return self.order.invoice_ids.invoice_line_ids.filtered(
            lambda line: line.product_id == self.product
        )

    def test_multiplicative_discount_and_invoice(self):
        self.line.write({"discount1": 10.0, "discount2": 20.0, "discount3": 30.0})
        self.assertAlmostEqual(self.line.discount, 49.6)
        self.assertAlmostEqual(self.line.price_subtotal, 302.4)
        invoice_line = self._invoice_line()
        self.assertAlmostEqual(invoice_line.discount1, 10.0)
        self.assertAlmostEqual(invoice_line.discount2, 20.0)
        self.assertAlmostEqual(invoice_line.discount3, 30.0)
        self.assertAlmostEqual(invoice_line.discount, 49.6)
        self.assertAlmostEqual(invoice_line.price_subtotal, self.line.price_subtotal)

    def test_additive_discount_is_flattened_on_invoice(self):
        self.line.write(
            {
                "discount1": 10.0,
                "discount2": 20.0,
                "discount3": 30.0,
                "discounting_type": "additive",
            }
        )
        self.assertAlmostEqual(self.line.discount, 60.0)
        self.assertAlmostEqual(self.line.price_subtotal, 240.0)
        invoice_line = self._invoice_line()
        self.assertAlmostEqual(invoice_line.discount1, 60.0)
        self.assertAlmostEqual(invoice_line.discount2, 0.0)
        self.assertAlmostEqual(invoice_line.discount3, 0.0)
        self.assertAlmostEqual(invoice_line.discount, 60.0)
        self.assertAlmostEqual(invoice_line.price_subtotal, self.line.price_subtotal)

    def test_standard_discount_wizard_updates_first_discount(self):
        self.line.write({"discount1": 10.0, "discount2": 20.0, "discount3": 30.0})
        self.env["sale.order.discount"].create(
            {
                "sale_order_id": self.order.id,
                "discount_percentage": 0.3,
                "discount_type": "sol_discount",
            }
        ).action_apply_discount()
        self.assertAlmostEqual(self.line.discount1, 30.0)
        self.assertAlmostEqual(self.line.discount2, 0.0)
        self.assertAlmostEqual(self.line.discount3, 0.0)
        self.assertAlmostEqual(self.line.discount, 30.0)

    def test_pricelist_discount_is_pulled_into_discount1(self):
        pricelist = self.env["product.pricelist"].create(
            {
                "name": "20 percent from quantity 50",
                "item_ids": [
                    Command.create(
                        {
                            "applied_on": "3_global",
                            "compute_price": "percentage",
                            "percent_price": 20.0,
                            "min_quantity": 50.0,
                        }
                    )
                ],
            }
        )
        self.order.pricelist_id = pricelist
        self.order._recompute_prices()
        self.assertAlmostEqual(self.line.discount1, 0.0)
        self.line.product_uom_qty = 51.0
        self.assertAlmostEqual(self.line.discount1, 20.0)
        self.assertAlmostEqual(self.line.discount2, 0.0)
        self.assertAlmostEqual(self.line.discount3, 0.0)
        self.assertAlmostEqual(self.line.discount, 20.0)

    def test_combo_line_precompute_discount(self):
        item_product = self.env["product.product"].create(
            {"name": "Combo Item", "type": "service", "invoice_policy": "order"}
        )
        combo = self.env["product.combo"].create(
            {
                "name": "Test Combo",
                "combo_item_ids": [Command.create({"product_id": item_product.id})],
            }
        )
        combo_product = self.env["product.product"].create(
            {
                "name": "Combo Product",
                "type": "combo",
                "list_price": 30.0,
                "combo_ids": [Command.set(combo.ids)],
            }
        )
        pricelist = self.env["product.pricelist"].create(
            {
                "name": "10 percent off",
                "item_ids": [
                    Command.create(
                        {
                            "applied_on": "3_global",
                            "compute_price": "percentage",
                            "percent_price": 10.0,
                        }
                    )
                ],
            }
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "pricelist_id": pricelist.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": combo_product.id,
                            "virtual_id": "combo_parent",
                            "product_uom_qty": 1.0,
                        }
                    ),
                    Command.create(
                        {
                            "product_id": item_product.id,
                            "combo_item_id": combo.combo_item_ids.id,
                            "linked_virtual_id": "combo_parent",
                            "price_unit": 30.0,
                        }
                    ),
                ],
            }
        )
        combo_line = order.order_line.filtered(
            lambda line: line.product_id == combo_product
        )
        item_line = order.order_line.filtered("combo_item_id")
        self.assertEqual(item_line.linked_line_id, combo_line)
        self.assertAlmostEqual(item_line.discount, combo_line.discount)
        self.assertAlmostEqual(item_line.discount, 10.0)
