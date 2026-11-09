from odoo.tests.common import TransactionCase


class TestPortalRequest(TransactionCase):
    def test_request_model_references_oca_contract_line(self):
        self.assertEqual(
            self.env["tl.sale.release.request"]._fields["line_id"].comodel_name,
            "sale.blanket.order.line",
        )
        self.assertEqual(
            self.env["tl.sale.release.request"]._fields["blanket_order_id"].comodel_name,
            "sale.blanket.order",
        )
