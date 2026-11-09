# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestManufacturedFor(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer_a = cls.env["res.partner"].create({"name": "Customer A", "is_company": True})
        cls.customer_b = cls.env["res.partner"].create({"name": "Customer B", "is_company": True})
        cls.contact_a = cls.env["res.partner"].create(
            {"name": "Purchaser A", "parent_id": cls.customer_a.id}
        )
        cls.product = cls.env["product.product"].create({
            "name": "Exclusive product A",
            "manufactured_for_partner_ids": [Command.set(cls.customer_a.ids)],
        })

    def test_partner_and_company_access(self):
        self.assertTrue(self.product._website_manufactured_accessible(self.customer_a))
        self.assertTrue(self.product._website_manufactured_accessible(self.contact_a))
        self.assertFalse(self.product._website_manufactured_accessible(self.customer_b))

    def test_confirmation_rejects_unauthorized_customer(self):
        order = self.env["sale.order"].create({
            "partner_id": self.customer_b.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1,
            })],
        })
        with self.assertRaises(ValidationError):
            order.action_confirm()
