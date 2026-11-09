# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestAdvanceLinkFields(TransactionCase):
    def test_oca_blanket_invoice_link_exists(self):
        self.assertIn('dimpal_blanket_order_id', self.env['account.move']._fields)
        self.assertIn('dimpal_blanket_order_id', self.env['purchase.order']._fields)
        self.assertTrue(hasattr(self.env['sale.order'], '_dimpal_get_blanket_order'))
