from odoo.tests.common import TransactionCase


class TestFiscalAdvanceContracts(TransactionCase):
    def test_advance_uses_distinct_contract_model(self):
        self.assertEqual(
            self.env["tl.sale.advance"]._fields["blanket_order_id"].comodel_name,
            "sale.blanket.order",
        )
        self.assertEqual(
            self.env["account.move.line"]._fields["tl_blanket_order_id"].comodel_name,
            "sale.blanket.order",
        )

    def test_mixed_invoice_does_not_require_single_header_contract(self):
        self.assertIn("tl_blanket_order_id", self.env["account.move.line"]._fields)
        self.assertIn("tl_allocation_ids", self.env["account.move"]._fields)
