# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts, mark_invoiced


@tagged("post_install", "-at_install")
class TestCertificationCorrections(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_construction_accounts(cls.env)
        cls.partner = cls.env["res.partner"].create({"name": "Correction Customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Correction Work",
            "type": "service",
            "list_price": 100.0,
        })
        cls.sale_order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.sale_line = cls.env["sale.order.line"].create({
            "order_id": cls.sale_order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
        })
        cls.sale_order.action_confirm()

    def _certify(self, qty, **vals):
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            **vals,
        })
        if qty:
            self.env["construction.certification.line"].create({
                "certification_id": cert.id,
                "sale_line_id": self.sale_line.id,
                "qty_period": qty,
            })
        return cert

    def test_draft_is_not_committed_and_approved_is(self):
        draft = self._certify(4.0)
        later = self._certify(2.0)
        self.assertEqual(later.line_ids.qty_origin, 2.0)
        self.assertEqual(later.amount_previously_invoiced, 0.0)
        draft.action_measure()
        draft.action_approve()
        later.invalidate_recordset()
        self.assertEqual(later.line_ids.qty_origin, 6.0)
        self.assertEqual(later.amount_previously_invoiced, 400.0)
        self.assertEqual(later.amount_to_invoice, 200.0)

    def test_percent_is_a_ratio_and_follows_the_quantity(self):
        cert = self._certify(2.0)
        self.assertAlmostEqual(cert.line_ids.percent_period, 0.2, places=4)
        cert.line_ids.write({"percent_period": 0.5})
        self.assertAlmostEqual(cert.line_ids.qty_period, 5.0, places=4)

    def test_invoiced_price_is_frozen_and_not_revalued(self):
        first = self._certify(4.0)
        mark_invoiced(first)
        self.sale_line.price_unit = 80.0
        self.assertEqual(first.line_ids.price_unit, 100.0)
        self.assertEqual(first.amount_certified_origin, 400.0)
        second = self._certify(1.0)
        self.assertEqual(second.line_ids.price_unit, 80.0)
        self.assertEqual(second.line_ids.amount_origin, 480.0)
        self.assertEqual(second.amount_previously_invoiced, 400.0)
        self.assertEqual(second.amount_to_invoice, 80.0)

    def test_date_cannot_move_before_an_invoiced_certification(self):
        first = self._certify(1.0, date="2026-06-01")
        mark_invoiced(first)
        with self.assertRaises(ValidationError):
            self._certify(1.0, date="2026-05-01")

    def test_approved_lines_are_locked(self):
        cert = self._certify(1.0)
        cert.action_measure()
        cert.action_approve()
        with self.assertRaises(UserError):
            cert.line_ids.write({"qty_period": 2.0})

    def test_normal_release_cannot_spend_retention_already_invoiced(self):
        cert = self._certify(5.0, retention_percent=10.0, retention_to_release=80.0)
        with self.assertRaises(UserError):
            cert.action_measure()

    def test_liquidation_cannot_release_the_same_retention_twice(self):
        first = self._certify(5.0, retention_percent=10.0, date="2026-06-01")
        self.assertEqual(first.amount_retention, 50.0)
        mark_invoiced(first)
        liquidation = self._certify(
            0.0,
            is_retention_liquidation=True,
            retention_to_release=50.0,
            date="2026-07-01",
        )
        self.assertEqual(liquidation.amount_certified_origin, 500.0)
        self.assertEqual(liquidation.amount_to_invoice, 50.0)
        liquidation.action_measure()
        liquidation.action_approve()
        mark_invoiced(liquidation)
        again = self._certify(
            0.0,
            is_retention_liquidation=True,
            retention_to_release=1.0,
            date="2026-08-01",
        )
        with self.assertRaises(UserError):
            again.action_measure()

    def test_liquidation_release_is_not_subtracted_from_later_production(self):
        first = self._certify(5.0, retention_percent=10.0, date="2026-06-01")
        mark_invoiced(first)
        liquidation = self._certify(
            0.0,
            is_retention_liquidation=True,
            retention_to_release=50.0,
            date="2026-07-01",
        )
        mark_invoiced(liquidation)
        later = self._certify(1.0, date="2026-08-01")
        self.assertEqual(later.amount_previously_invoiced, 500.0)
        self.assertEqual(later.amount_to_invoice, 100.0)

    def test_sales_order_invoicing_leaves_uncertified_lines(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        certified_line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.product.id,
            "product_uom_qty": 4.0,
            "price_unit": 100.0,
        })
        free_line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "price_unit": 25.0,
        })
        order.action_confirm()
        cert = self.env["construction.certification"].create({"sale_order_id": order.id})
        self.env["construction.certification.line"].create({
            "certification_id": cert.id,
            "sale_line_id": certified_line.id,
            "qty_period": 1.0,
        })
        certified_line.invalidate_recordset()
        free_line.invalidate_recordset()
        self.assertAlmostEqual(certified_line.qty_to_invoice, 3.0, places=2)
        self.assertAlmostEqual(free_line.qty_to_invoice, 1.0, places=2)
        invoiceable = order._get_invoiceable_lines()
        self.assertIn(certified_line, invoiceable)
        self.assertIn(free_line, invoiceable)

    def test_origin_invoice_posts_retention_advance_and_taxes_apart_from_income(self):
        tax = self.env["account.tax"].create({
            "name": "Construction 21",
            "amount": 21.0,
            "type_tax_use": "sale",
        })
        self.sale_line.tax_ids = tax
        self.product.list_price = 999.0
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 50.0,
        })
        advance.action_confirm()
        advance.action_create_invoice()
        advance.invoice_id.action_post()
        cert = self._certify(5.0, retention_percent=10.0, amount_advance_applied=50.0)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        invoice = cert.invoice_id
        product_line = invoice.invoice_line_ids.filtered(lambda line: line.product_id == self.product)
        self.assertEqual(product_line.tax_ids, tax)
        self.assertAlmostEqual(product_line.price_unit, 100.0, places=2)
        self.assertFalse(product_line.sale_line_ids)
        retention_line = invoice.invoice_line_ids.filtered(
            lambda line: line.construction_adjustment_type == "retention"
        )
        self.assertEqual(
            retention_line.account_id,
            self.env.company.construction_retention_account_id,
        )
        self.assertFalse(retention_line.tax_ids)
        self.assertAlmostEqual(retention_line.price_unit, -50.0, places=2)
        advance_line = invoice.invoice_line_ids.filtered("construction_advance_application_id")
        self.assertEqual(
            advance_line.account_id,
            self.env.company.construction_advance_account_id,
        )
        self.assertEqual(advance_line.tax_ids, tax)
        self.assertAlmostEqual(advance_line.price_unit, -50.0, places=2)
        self.assertEqual(invoice.document_tax_mode, "tax_excluded")
        self.assertAlmostEqual(invoice.amount_untaxed, 400.0, places=2)
        # VAT on the certified base minus the advance base. Retention is outside VAT.
        self.assertAlmostEqual(invoice.amount_total - invoice.amount_untaxed, 94.5, places=2)
        self.assertTrue(self.env.company.construction_advance_account_id.reconcile)

    def test_date_cannot_precede_an_approved_certification(self):
        first = self._certify(1.0, date="2026-06-01")
        first.action_measure()
        first.action_approve()
        with self.assertRaises(ValidationError):
            self._certify(1.0, date="2026-05-01")

    def test_quantities_cannot_exceed_the_budget_across_certifications(self):
        self._certify(6.0)
        with self.assertRaises(ValidationError):
            self._certify(6.0)

    def test_deleting_a_certification_does_not_reuse_its_number(self):
        first = self._certify(1.0)
        second = self._certify(1.0)
        third = self._certify(1.0)
        second.unlink()
        nxt = self._certify(1.0)
        self.assertEqual(first.certification_number, 1)
        self.assertEqual(third.certification_number, 3)
        self.assertEqual(nxt.certification_number, 4)

    def test_discount_is_removed_from_the_certified_price(self):
        self.sale_line.discount = 10.0
        cert = self._certify(2.0)
        self.assertAlmostEqual(cert.line_ids.price_unit, 90.0, places=2)
        self.assertAlmostEqual(cert.line_ids.amount_period, 180.0, places=2)

    def test_tax_included_order_is_certified_on_the_excluded_base(self):
        tax = self.env["account.tax"].create({
            "name": "Included 21",
            "amount": 21.0,
            "type_tax_use": "sale",
        })
        self.sale_order.document_tax_mode = "tax_included"
        self.sale_line.write({"price_unit": 121.0, "tax_ids": [(6, 0, [tax.id])]})
        cert = self._certify(1.0, retention_percent=0.0)
        self.assertAlmostEqual(cert.line_ids.price_unit, self.sale_line.price_reduce_taxexcl, places=2)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        self.assertEqual(cert.invoice_id.document_tax_mode, "tax_excluded")
        self.assertAlmostEqual(cert.invoice_id.amount_untaxed, cert.amount_final_to_invoice, places=2)

    def test_cancelling_an_earlier_approval_does_not_rewrite_a_later_one(self):
        earlier = self._certify(4.0, date="2026-06-01")
        earlier.action_measure()
        earlier.action_approve()
        later = self._certify(2.0, date="2026-07-01")
        later.action_measure()
        later.action_approve()
        self.assertEqual(later.amount_previously_invoiced, 400.0)
        earlier.action_cancel()
        later.invalidate_recordset()
        self.assertEqual(later.amount_previously_invoiced, 400.0)
        self.assertEqual(later.amount_to_invoice, 200.0)
        later.action_draft()
        later.invalidate_recordset()
        self.assertEqual(later.amount_previously_invoiced, 0.0)
        self.assertEqual(later.amount_to_invoice, 200.0)

    def test_invoiced_certification_keeps_its_state(self):
        cert = self._certify(1.0)
        mark_invoiced(cert)
        with self.assertRaises(UserError):
            cert.write({"state": "draft"})

    def test_invoiced_certification_increases_qty_invoiced(self):
        cert = self._certify(4.0)
        mark_invoiced(cert)
        self.sale_line.invalidate_recordset()
        self.assertAlmostEqual(self.sale_line.qty_invoiced, 4.0, places=2)
        self.assertAlmostEqual(self.sale_line.qty_to_invoice, 6.0, places=2)
        self.assertEqual(self.sale_line.invoice_status, "to invoice")

    def test_invoice_line_keeps_the_sale_analytic_distribution(self):
        if "analytic_distribution" not in self.sale_line._fields:
            self.skipTest("analytic is not installed")
        plan = self.env["account.analytic.plan"].search([], limit=1)
        if not plan:
            plan = self.env["account.analytic.plan"].create({"name": "Construction"})
        analytic = self.env["account.analytic.account"].create({
            "name": "Site",
            "plan_id": plan.id,
        })
        self.sale_line.analytic_distribution = {str(analytic.id): 100.0}
        cert = self._certify(1.0, retention_percent=10.0)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        product_line = cert.invoice_id.invoice_line_ids.filtered(
            lambda line: line.product_id and line.construction_adjustment_type != "rounding"
        )
        self.assertEqual(product_line.analytic_distribution.get(str(analytic.id)), 100.0)
        self.assertEqual(product_line.quantity, cert.line_ids.qty_period)
        retention_line = cert.invoice_id.invoice_line_ids.filtered(
            lambda line: line.construction_adjustment_type == "retention"
        )
        self.assertEqual(retention_line.analytic_distribution.get(str(analytic.id)), 100.0)

    def test_cannot_mark_invoiced_without_an_invoice(self):
        cert = self._certify(1.0)
        with self.assertRaises(UserError):
            cert.write({"state": "invoiced"})

    def test_invoice_keeps_the_measured_quantity(self):
        cert = self._certify(3.0)
        quantity, _unit = cert.line_ids._invoice_quantity_price()
        self.assertEqual(quantity, 3.0)

    def test_approved_amount_stays_when_recomputed(self):
        cert = self._certify(4.0)
        cert.action_measure()
        cert.action_approve()
        self.sale_line.price_unit = 50.0
        cert.line_ids._compute_origin()
        cert.line_ids._compute_amounts()
        cert._compute_amounts()
        self.assertEqual(cert.amount_to_invoice, 400.0)

    def test_taxed_advance_cannot_be_deducted_before_its_invoice_is_posted(self):
        tax = self.env["account.tax"].create({
            "name": "Advance 21",
            "amount": 21.0,
            "type_tax_use": "sale",
        })
        self.sale_line.tax_ids = tax
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 50.0,
        })
        advance.action_confirm()
        cert = self._certify(1.0, retention_percent=0.0, amount_advance_applied=50.0)
        cert.action_measure()
        cert.action_approve()
        with self.assertRaises(UserError):
            cert.action_create_invoice()


