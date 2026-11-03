from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestGeneralVatScope(TransactionCase):
    def test_advance_invoice_rejects_cash_basis_taxes_and_groups(self):
        Tax = self.env["account.tax"]
        normal = Tax.create({
            "name": "Normal general VAT test",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 21,
            "tax_exigibility": "on_invoice",
        })
        cash = Tax.create({
            "name": "Cash basis unsupported test",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 21,
            "tax_exigibility": "on_payment",
        })
        group = Tax.create({
            "name": "Group containing cash basis test",
            "type_tax_use": "sale",
            "amount_type": "group",
            "children_tax_ids": [(6, 0, [cash.id])],
        })
        configure_construction_accounts(self.env)
        partner = self.env["res.partner"].create({"name": "VAT scope customer"})
        order = self.env["sale.order"].create({"partner_id": partner.id})

        def create_advance(tax):
            advance = self.env["construction.advance"].create({
                "sale_order_id": order.id,
                "amount": 100.0,
                "tax_ids": [(6, 0, [tax.id])],
            })
            advance.action_confirm()
            return advance

        for tax in cash | group:
            with self.assertRaises(UserError):
                create_advance(tax).action_create_invoice()
        regular = create_advance(normal)
        with self.assertRaisesRegex(UserError, "payment"):
            regular.action_create_invoice()
        self.assertFalse(regular.invoice_id)
