# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.packaging import _tl_whole_package_quantity
from ..models.product_template import _tl_contract_availability_rows


@tagged("post_install", "-at_install")
class TestContractPackaging(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buyer = cls.env["res.partner"].create({"name": "Packaging customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Contract product in boxes", "list_price": 1.2,
            "tl_contract_whole_pack_only": True,
        })
        unit = cls.product.uom_id
        cls.box = cls.env["uom.uom"].create({
            "name": "Case of 12", "relative_factor": 12,
            "relative_uom_id": unit.id,
        })
        cls.pallet = cls.env["uom.uom"].create({
            "name": "Pallet of 120", "relative_factor": 120,
            "relative_uom_id": unit.id,
        })
        cls.product.write({
            "uom_ids": [Command.set([cls.box.id, cls.pallet.id])],
        })
        today = fields.Date.today()
        cls.contract = cls.env["sale.blanket.order"].create({
            "partner_id": cls.buyer.id,
            "pricelist_id": cls.buyer.property_product_pricelist.id,
            "validity_start_date": today - timedelta(days=1),
            "validity_date": today + timedelta(days=30),
            "line_ids": [Command.create({
                "product_id": cls.product.id,
                "original_uom_qty": 1000,
                "product_uom": unit.id,
                "price_unit": 0.80,
            })],
        })
        cls.contract.action_confirm()
        cls.line = cls.contract.line_ids

    def _summary(self, uom):
        return _tl_contract_availability_rows(
            self.line, "es_ES", selected_uom=uom, product=self.product,
        )[0]

    def test_boxes_and_remainder_never_round_up(self):
        row = self._summary(self.box)
        self.assertEqual(row["quantity"], 1000)
        self.assertEqual(row["full_packages"], 83)
        self.assertEqual(row["maximum_orderable_qty"], 83)
        self.assertEqual(row["package_size_in_base"], 12)
        self.assertAlmostEqual(row["leftover_base_qty"], 4)
        self.assertAlmostEqual(self.line._tl_price_for_uom(self.box), 9.60)
        self.assertTrue(self.line._tl_available_for_sale_line(83, self.box))
        self.assertFalse(self.line._tl_available_for_sale_line(84, self.box))

    def test_pallets_and_units_share_one_contract_balance(self):
        row = self._summary(self.pallet)
        self.assertEqual(row["full_packages"], 8)
        self.assertAlmostEqual(row["leftover_base_qty"], 40)
        unit = self._summary(self.product.uom_id)
        self.assertEqual(unit["maximum_orderable_qty"], 1000)
        self.assertFalse(unit["is_packaging"])
        self.assertAlmostEqual(self.line._tl_price_for_uom(self.pallet), 96.0)

    def test_whole_packages_enforced_on_server(self):
        sale = self.env["sale.order"].create({"partner_id": self.buyer.id})
        sale._tl_check_contract_packaging(self.product, self.box, 2)
        sale._tl_check_contract_packaging(self.product, self.product.uom_id, 2.5)
        with self.assertRaises(UserError):
            sale._tl_check_contract_packaging(self.product, self.box, 2.5)
        self.product.tl_contract_whole_pack_only = False
        sale._tl_check_contract_packaging(self.product, self.box, 2.5)
        row = self._summary(self.box)
        self.assertAlmostEqual(row["maximum_orderable_qty"], 1000 / 12)

    def test_mixed_sale_lines_consume_contract_in_source_uom(self):
        order = self.env["sale.order"].create({"partner_id": self.buyer.id})
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "product_uom_qty": 2, "product_uom_id": self.box.id,
            "blanket_order_line": self.line.id,
        })
        self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "product_uom_qty": 5, "product_uom_id": self.product.uom_id.id,
            "blanket_order_line": self.line.id,
        })
        self.line.invalidate_recordset(["remaining_uom_qty"])
        # 2 boxes of 12 + 5 singles consume 29 of the same 1,000 units.
        self.assertAlmostEqual(self.line.remaining_uom_qty, 971)
        self.assertEqual(self._summary(self.box)["full_packages"], 80)

    def test_invalid_pack_quantities_are_rejected(self):
        self.assertTrue(_tl_whole_package_quantity(83.0))
        self.assertFalse(_tl_whole_package_quantity(83.5))
        self.assertFalse(_tl_whole_package_quantity(0))
        self.assertFalse(_tl_whole_package_quantity(float("inf")))
        self.assertFalse(_tl_whole_package_quantity(float("nan")))

    def test_contract_visibility_is_customer_specific(self):
        stranger = self.env["res.partner"].create({"name": "Not allowed"})
        allowed = self.env["sale.blanket.order.line"]._tl_website_candidates(
            self.product, self.buyer, self.env.company, self.contract.currency_id,
        )
        denied = self.env["sale.blanket.order.line"]._tl_website_candidates(
            self.product, stranger, self.env.company, self.contract.currency_id,
        )
        self.assertIn(self.line, allowed)
        self.assertFalse(denied)
        self.assertEqual(_tl_contract_availability_rows(
            denied, "ca_ES", selected_uom=self.box, product=self.product,
        ), [])
