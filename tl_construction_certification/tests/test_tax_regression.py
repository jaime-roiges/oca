# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestTaxRegression(TransactionCase):
    """Locks the two tax rules that have regressed.

    A standard compute must not gain a dependency that fires on every
    invoice. An empty tax set on the budget is an exemption.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_construction_accounts(cls.env)
        cls.tax = cls.env["account.tax"].create({
            "name": "Certification VAT 21",
            "amount": 21.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
        })
        cls.other_tax = cls.env["account.tax"].create({
            "name": "Certification VAT 10",
            "amount": 10.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
        })
        cls.partner = cls.env["res.partner"].create({"name": "Tax Regression Customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Taxed Work",
            "type": "service",
            "list_price": 100.0,
            "taxes_id": [(6, 0, [cls.tax.id])],
        })
        cls.sale_order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.sale_line = cls.env["sale.order.line"].create({
            "order_id": cls.sale_order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
            "tax_ids": [(6, 0, [cls.tax.id])],
        })
        cls.sale_order.action_confirm()

    def _line(self):
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
        })
        return self.env["construction.certification.line"].create({
            "certification_id": cert.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 1.0,
        })

    def test_tax_compute_does_not_depend_on_product_taxes_or_fiscal_position(self):
        depends = self.env["account.move.line"]._fields["tax_ids"].depends
        self.assertIn("product_id", depends)
        self.assertNotIn("product_id.taxes_id", depends)
        self.assertNotIn("move_id.fiscal_position_id", depends)

    def test_matching_budget_uses_the_product_tax(self):
        line = self._line()
        self.assertEqual(line._mapped_sale_taxes(), self.tax)

    def test_cleared_budget_tax_is_an_exemption(self):
        self.sale_line.tax_ids = False
        line = self._line()
        self.assertFalse(line._mapped_sale_taxes())

    def test_changed_budget_tax_is_kept(self):
        self.sale_line.tax_ids = self.other_tax
        line = self._line()
        self.assertEqual(line._mapped_sale_taxes(), self.other_tax)
