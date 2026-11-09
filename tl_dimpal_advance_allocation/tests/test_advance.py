# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from ast import literal_eval
from odoo.tests.common import TransactionCase


class TestAdvanceLinkFields(TransactionCase):
    def test_oca_blanket_invoice_link_exists(self):
        self.assertIn('dimpal_blanket_order_id', self.env['account.move']._fields)
        self.assertIn('dimpal_blanket_order_id', self.env['purchase.order']._fields)
        self.assertTrue(hasattr(self.env['sale.order'], '_dimpal_get_blanket_order'))

    def test_configured_accounts_domains_odoo20(self):
        accounts = self.env['account.account']
        for field_name, expected_type in (
            ('dimpal_customer_advance_account_id', 'liability_current'),
            ('dimpal_supplier_advance_account_id', 'asset_current'),
        ):
            field = self.env['res.company']._fields[field_name]
            domain = literal_eval(field.domain)
            self.assertTrue(field.check_company)
            self.assertIn(('active', '=', True), domain)
            self.assertIn(('account_type', '=', expected_type), domain)
            self.assertTrue(all(term[0] in accounts._fields for term in domain))
