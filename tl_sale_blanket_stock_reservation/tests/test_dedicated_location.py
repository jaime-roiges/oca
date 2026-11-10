# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBlanketDedicatedLocation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([
            ("company_id", "=", cls.env.company.id)
        ], limit=1)
        cls.partner = cls.env["res.partner"].create({"name": "Stock customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Protected item", "type": "consu", "is_storable": True,
        })
        today = fields.Date.today()
        cls.agreement = cls.env["sale.blanket.order"].create({
            "partner_id": cls.partner.id,
            "pricelist_id": cls.partner.property_product_pricelist.id,
            "validity_start_date": today - timedelta(days=1),
            "validity_date": today + timedelta(days=30),
            "line_ids": [Command.create({
                "product_id": cls.product.id, "original_uom_qty": 1000,
                "product_uom": cls.product.uom_id.id, "price_unit": 1.5,
            })],
        })
        cls.agreement.action_confirm()
        cls.line = cls.agreement.line_ids
        cls.line.tl_dedicated_warehouse_id = cls.warehouse

    def test_location_is_outside_regular_stock(self):
        self.assertTrue(self.warehouse)
        location = self.line._tl_get_or_create_dedicated_location()
        self.assertEqual(location.usage, "internal")
        self.assertEqual(location.tl_blanket_line_id, self.line)
        self.assertTrue(location._child_of(self.warehouse.view_location_id))
        self.assertFalse(location._child_of(self.warehouse.lot_stock_id))
        self.assertEqual(self.line._tl_get_or_create_dedicated_location(), location)
