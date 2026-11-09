# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestBlanketIntegration(TransactionCase):
    def test_portal_visibility_is_boolean_field(self):
        self.assertIn('dimpal_portal_visible', self.env['sale.order']._fields)
        self.assertIn('dimpal_blanket_order_id', self.env['purchase.order']._fields)

    def test_oca_fields_not_reimplemented(self):
        self.assertIn('blanket_order_id', self.env['sale.order']._fields)
        self.assertIn('call_off_remaining_qty', self.env['sale.order.line']._fields)
