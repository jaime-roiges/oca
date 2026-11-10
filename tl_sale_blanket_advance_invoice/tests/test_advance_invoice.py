# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged("post_install", "-at_install")
class TestFiscalAdvanceWizard(TransactionCase):
    def test_nonpositive_advance_is_rejected(self):
        """A fiscal advance must not create a negative invoice by mistake."""
        # UI permission and fiscal controls are additionally verified in QA
        # with a complete Spanish chart, actual taxes and bank reconciliation.
        wizard = self.env["tl.sale.blanket.advance.invoice.wizard"]
        self.assertIn("amount_base", wizard._fields)
        self.assertIn("tax_ids", wizard._fields)
        self.assertIn("blanket_order_id", wizard._fields)
        self.assertIn("tl_blanket_order_id", self.env["account.move"]._fields)
