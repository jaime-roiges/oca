# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestPortalBlanket(TransactionCase):
    def test_oca_wizard_and_portal_fields(self):
        self.assertIn('call_off_remaining_qty', self.env['sale.order.line']._fields)
        self.assertIn('dimpal_portal_visible', self.env['sale.order']._fields)
        self.assertIn('wizard_line_ids', self.env['sale.order.deliver.remaining.wizard']._fields)
