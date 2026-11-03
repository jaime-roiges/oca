from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestRetentionDue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_construction_accounts(cls.env)
        cls.customer = cls.env["res.partner"].create({"name": "Retention maturity test"})
        cls.product = cls.env["product.product"].create({
            "name": "Retention maturity work", "type": "service", "invoice_policy": "order",
        })
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.customer.id,
            "construction_retention_due_date": "2030-06-30",
        })
        cls.sale_line = cls.env["sale.order.line"].create({
            "order_id": cls.order.id, "product_id": cls.product.id,
            "product_uom_qty": 10, "price_unit": 100, "tax_ids": [(6, 0, [])],
        })
        cls.order.action_confirm()

    def _certification(self, **values):
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "retention_percent": 10.0, **values,
        })
        self.env["construction.certification.line"].create({
            "certification_id": cert.id, "sale_line_id": self.sale_line.id, "qty_period": 4,
        })
        cert.action_measure()
        cert.action_approve()
        return cert

    def test_requires_date_and_no_retention_exception(self):
        cert = self._certification(retention_due_date=False)
        with self.assertRaises(UserError):
            cert.action_create_invoice()
        self.assertFalse(cert.invoice_id)
        without_retention = self._certification(retention_due_date=False, retention_percent=0.0)
        without_retention.action_create_invoice()
        self.assertTrue(without_retention.invoice_id)

    def test_order_default_can_be_overridden(self):
        cert = self._certification(retention_due_date="2031-01-10")
        self.assertEqual(cert.retention_due_date, date(2031, 1, 10))
        cert.action_create_invoice()
        line = cert.invoice_id.invoice_line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        self.assertEqual(len(line), 1)
        self.assertEqual(line.date_maturity, date(2031, 1, 10))

    def test_posted_and_partial_release_preserve_open_maturity(self):
        cert = self._certification()
        self.assertEqual(cert.retention_due_date, date(2030, 6, 30))
        cert.action_create_invoice()
        invoice = cert.invoice_id
        retention = invoice.invoice_line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        self.assertEqual(len(retention), 1)
        invoice.action_post()
        self.assertEqual(retention.date_maturity, date(2030, 6, 30))
        receivables = invoice.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
        payment_due_dates = receivables.mapped("date_maturity")

        liquidation = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "is_retention_liquidation": True, "retention_to_release": 10,
        })
        liquidation.action_measure()
        liquidation.action_approve()
        liquidation.action_create_invoice()
        liquidation.invoice_id.action_post()
        retention.invalidate_recordset()
        self.assertFalse(retention.reconciled)
        self.assertAlmostEqual(retention.amount_residual, 30.0, places=2)
        cert.write({"retention_due_date": "2031-02-01"})
        self.assertEqual(retention.date_maturity, date(2031, 2, 1))
        self.assertEqual(receivables.mapped("date_maturity"), payment_due_dates)

    def test_reversal_keeps_original_date(self):
        cert = self._certification()
        cert.action_create_invoice()
        cert.invoice_id.action_post()
        refund = cert.invoice_id._reverse_moves(cancel=False)
        retained = refund.invoice_line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained.date_maturity, date(2030, 6, 30))

    def test_cannot_release_retention_from_draft_invoice(self):
        cert = self._certification()
        cert.action_create_invoice()
        release = self.env["construction.certification"].create({
            "sale_order_id": self.order.id,
            "is_retention_liquidation": True,
            "retention_to_release": 10,
        })
        with self.assertRaises(UserError):
            release.action_measure()
        cert.invoice_id.action_post()
        release.action_measure()

    def test_draft_liquidation_reserves_retention(self):
        cert = self._certification()
        cert.action_create_invoice()
        cert.invoice_id.action_post()
        first = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "is_retention_liquidation": True,
            "retention_to_release": 30,
        })
        first.action_measure()
        first.action_approve()
        first.action_create_invoice()
        second = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "is_retention_liquidation": True,
            "retention_to_release": 15,
        })
        with self.assertRaises(UserError):
            second.action_measure()

    def test_manual_partial_reconciliation_reduces_available_retention(self):
        cert = self._certification()
        cert.action_create_invoice()
        invoice = cert.invoice_id
        invoice.action_post()
        retention = invoice.line_ids.filtered(lambda line: line.construction_adjustment_type == "retention")
        other_account = invoice.invoice_line_ids.filtered(
            lambda line: line.account_id != retention.account_id
        )[:1].account_id
        entry = self.env["account.move"].create({
            "move_type": "entry", "journal_id": invoice.journal_id.id,
            "date": invoice.date, "line_ids": [
                (0, 0, {"account_id": retention.account_id.id,
                        "partner_id": retention.partner_id.id, "credit": 20}),
                (0, 0, {"account_id": other_account.id, "debit": 20}),
            ],
        })
        entry.action_post()
        (retention | entry.line_ids.filtered(lambda line: line.account_id == retention.account_id)).reconcile()
        liquidation = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "is_retention_liquidation": True,
            "retention_to_release": 25,
        })
        self.assertAlmostEqual(liquidation._retention_held_from_previous(), 20, places=2)
        with self.assertRaises(UserError):
            liquidation.action_measure()

    def test_mixed_taxes_require_review_even_through_write(self):
        tax = self.env["account.tax"].create({
            "name": "Mixed tax test", "amount": 10, "type_tax_use": "sale",
        })
        self.env["sale.order.line"].create({
            "order_id": self.order.id, "product_id": self.product.id,
            "product_uom_qty": 1, "price_unit": 10, "tax_ids": [(6, 0, [tax.id])],
        })
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.order.id, "amount": 50,
        })
        self.assertFalse(advance.tax_ids)
        with self.assertRaises(UserError):
            advance.write({"state": "confirmed"})
        advance.write({"tax_ids": [(6, 0, [tax.id])], "mixed_taxes_confirmed": True})
        advance.action_confirm()

    def test_changed_account_does_not_strand_existing_retention(self):
        cert = self._certification()
        cert.action_create_invoice()
        cert.invoice_id.action_post()
        old = self.env.company.construction_retention_account_id
        new = self.env["account.account"].create({
            "name": "New retention account",
            "code": "449099",
            "account_type": "asset_current",
            "reconcile": True,
            "company_ids": [(6, 0, [self.env.company.id])],
        })
        self.env.company.construction_retention_account_id = new
        release = self.env["construction.certification"].create({
            "sale_order_id": self.order.id,
            "is_retention_liquidation": True,
            "retention_to_release": 10,
        })
        release.action_measure()
        release.action_approve()
        release.action_create_invoice()
        line = release.invoice_id.invoice_line_ids.filtered(
            lambda l: l.construction_adjustment_type == "retention_release"
        )
        self.assertEqual(line.account_id, old)
        release.invoice_id.action_post()
        self.assertTrue(line.reconciled)
        with self.assertRaises(UserError):
            cert.action_cancel()

    def test_changed_advance_account_uses_original_liability(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.order.id, "amount": 50,
            "tax_ids": [(6, 0, [])],
        })
        advance.action_confirm()
        advance.action_create_invoice()
        advance.invoice_id.action_post()
        old = self.env.company.construction_advance_account_id
        new = self.env["account.account"].create({
            "name": "New advance account", "code": "438099",
            "account_type": "liability_current", "reconcile": True,
            "company_ids": [(6, 0, [self.env.company.id])],
        })
        self.env.company.construction_advance_account_id = new
        cert = self._certification(retention_percent=0, amount_advance_applied=50)
        cert.action_create_invoice()
        deduction = cert.invoice_id.invoice_line_ids.filtered("construction_advance_application_id")
        self.assertEqual(deduction.account_id, old)
        cert.invoice_id.action_post()
        self.assertTrue(deduction.reconciled)

    def test_selected_retentions_split_across_accounts_and_reconcile(self):
        first = self._certification()
        first.action_create_invoice()
        first.invoice_id.action_post()
        source1 = first.invoice_id.line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        new_account = self.env["account.account"].create({
            "name": "Another retention account", "code": "449098",
            "account_type": "asset_current", "reconcile": True,
            "company_ids": [(6, 0, [self.env.company.id])],
        })
        self.env.company.construction_retention_account_id = new_account
        second = self._certification()
        second.action_create_invoice()
        second.invoice_id.action_post()
        source2 = second.invoice_id.line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        release = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "is_retention_liquidation": True,
            "retention_to_release": 30,
        })
        self.env["construction.retention.allocation"].create([
            {"certification_id": release.id, "source_line_id": source1.id, "amount": 10},
            {"certification_id": release.id, "source_line_id": source2.id, "amount": 20},
        ])
        release.action_measure()
        release.action_approve()
        release.action_create_invoice()
        lines = release.invoice_id.invoice_line_ids.filtered("construction_retention_allocation_id")
        self.assertEqual(len(lines), 2)
        self.assertEqual(set(lines.mapped("account_id").ids), {source1.account_id.id, source2.account_id.id})
        self.assertEqual(sorted(lines.mapped("price_subtotal")), [10, 20])
        release.invoice_id.action_post()
        self.assertTrue(all(lines.mapped("reconciled")))
        self.assertAlmostEqual(source1.amount_residual_currency, 30, places=2)
        self.assertAlmostEqual(source2.amount_residual_currency, 20, places=2)
        with self.assertRaises(UserError):
            first.invoice_id._reverse_moves(cancel=False)

    def test_allocation_must_match_requested_release(self):
        first = self._certification()
        first.action_create_invoice()
        first.invoice_id.action_post()
        source = first.invoice_id.line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        release = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "is_retention_liquidation": True,
            "retention_to_release": 20,
        })
        self.env["construction.retention.allocation"].create({
            "certification_id": release.id, "source_line_id": source.id, "amount": 10,
        })
        with self.assertRaises(UserError):
            release.action_measure()

    def test_allocation_rejects_a_source_reserved_by_another_draft(self):
        first = self._certification()
        first.action_create_invoice()
        first.invoice_id.action_post()
        source = first.invoice_id.line_ids.filtered(lambda l: l.construction_adjustment_type == "retention")
        def release(amount):
            record = self.env["construction.certification"].create({
                "sale_order_id": self.order.id, "is_retention_liquidation": True,
                "retention_to_release": amount,
            })
            self.env["construction.retention.allocation"].create({
                "certification_id": record.id, "source_line_id": source.id, "amount": amount,
            })
            return record
        first_release = release(30)
        first_release.action_measure()
        first_release.action_approve()
        first_release.action_create_invoice()
        with self.assertRaises(UserError):
            release(15).action_measure()
