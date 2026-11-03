from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestCollectedAdvance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = configure_construction_accounts(cls.env)
        cls.partner = cls.env["res.partner"].create({"name": "Collected advance customer"})
        cls.order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.journal = cls.env["account.journal"].search([
            ("company_id", "=", cls.company.id), ("type", "=", "bank"),
        ], limit=1)
        assert cls.journal and cls.journal.default_account_id, "A configured bank journal is required"
        cls.method = cls.journal.inbound_payment_method_line_ids[:1]
        assert cls.method, "An inbound payment method is required"
        # Direct bank accounting is a standard Odoo payment configuration.
        cls.method.payment_account_id = cls.journal.default_account_id
        cls.tax = cls.env["account.tax"].search([
            ("company_id", "=", cls.company.id), ("type_tax_use", "=", "sale"),
            ("amount_type", "=", "percent"), ("amount", "=", 21),
            ("tax_exigibility", "=", "on_invoice"),
        ], limit=1)
        assert cls.tax, "A 21% general-regime sales tax is required"

    def _payment(self, amount):
        payment = self.env["account.payment"].create({
            "company_id": self.company.id,
            "partner_id": self.partner.id,
            "payment_type": "inbound", "partner_type": "customer",
            "journal_id": self.journal.id,
            "payment_method_line_id": self.method.id,
            "amount": amount, "date": "2026-06-01",
        })
        payment.action_post()
        return payment

    def _advance(self, payment, base=50.0):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.order.id, "amount": base,
            "collection_payment_id": payment.id,
            "collection_date": "2026-06-01",
            "tax_ids": [(6, 0, self.tax.ids)],
        })
        advance.action_confirm()
        return advance

    def test_partial_receipts_produce_separate_reconciled_invoices(self):
        for index in range(2):
            payment = self._payment(60.50)
            advance = self._advance(payment)
            advance.action_create_invoice()
            invoice = advance.invoice_id
            self.assertAlmostEqual(invoice.amount_untaxed, 50.0, places=2)
            self.assertAlmostEqual(invoice.amount_tax, 10.50, places=2)
            self.assertEqual(str(invoice.delivery_date), "2026-06-01")
            self.assertGreaterEqual(invoice.invoice_date, invoice.delivery_date)
            invoice.action_post()
            self.assertEqual(str(invoice.date), "2026-06-01")
            advance.action_reconcile_received_payment()
            self.assertTrue(invoice.currency_id.is_zero(invoice.amount_residual))
            self.assertIn(payment, invoice._get_reconciled_payments())
            if hasattr(invoice, "_l10n_es_edi_get_invoices_info"):
                # Build the official payload in memory; do not send it.
                sii_info = invoice._l10n_es_edi_get_invoices_info()[0]
                sii = sii_info["FacturaExpedida"]
                self.assertAlmostEqual(sii["ImporteTotal"], 60.50, places=2)
                self.assertEqual(sii_info["PeriodoLiquidacion"]["Ejercicio"], "2026")
                expected_period = "2T" if (
                    "account_return_periodicity" in self.company._fields
                    and self.company.account_return_periodicity == "trimester"
                ) else "06"
                self.assertEqual(sii_info["PeriodoLiquidacion"]["Periodo"], expected_period)
                if invoice.invoice_date != invoice.delivery_date:
                    self.assertEqual(sii["FechaOperacion"], "01-06-2026")
            if hasattr(invoice, "_l10n_es_edi_verifactu_get_record_values"):
                # Build the official tax data in memory; do not send it.
                vals = invoice._l10n_es_edi_verifactu_get_record_values()
                self.assertFalse(vals["errors"])
                self.assertEqual(vals["delivery_date"], invoice.delivery_date)
                self.assertAlmostEqual(vals["tax_details"]["base_amount"], 50.0, places=2)
                self.assertAlmostEqual(vals["tax_details"]["tax_amount"], 10.50, places=2)

    def test_invoice_cannot_exceed_collected_amount(self):
        payment = self._payment(60.50)
        advance = self._advance(payment, base=100.0)
        with self.assertRaises(UserError), self.cr.savepoint():
            advance.action_create_invoice()
        self.assertFalse(advance.invoice_id)
