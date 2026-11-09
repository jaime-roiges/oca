from odoo.tests.common import TransactionCase


class TestBlanketIntegration(TransactionCase):
    def test_oca_contract_is_canonical(self):
        self.assertIn("tl_portal_visible", self.env["sale.blanket.order"]._fields)
        self.assertIn("tl_blanket_order_id", self.env["purchase.order"]._fields)
        self.assertEqual(
            self.env["purchase.order"]._fields["tl_blanket_order_id"].comodel_name,
            "sale.blanket.order",
        )

    def test_sale_lines_support_individual_contracts(self):
        self.assertIn("blanket_order_line", self.env["sale.order.line"]._fields)
