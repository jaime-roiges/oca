from odoo.tests.common import TransactionCase


class TestCreditCheckout(TransactionCase):
    def test_sale_order_line_supports_blanket_line(self):
        self.assertEqual(
            self.env["sale.order.line"]._fields["blanket_order_line"].comodel_name,
            "sale.blanket.order.line",
        )

    def test_credit_opt_in_field_exists(self):
        self.assertIn("skip_website_checkout_payment", self.env["res.partner"]._fields)
