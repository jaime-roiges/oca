# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import inspect

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts, mark_invoiced


@tagged("post_install", "-at_install")
class TestAllBugRegressions(TransactionCase):
    """One regression test per bug that has been closed.

    Behavioural tests cover the money path. Source and dependency checks
    cover the rules that only fail when a standard compute is edited.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_construction_accounts(cls.env)
        cls.tax = cls.env["account.tax"].create({
            "name": "Regression VAT 21",
            "amount": 21.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
        })
        cls.other_tax = cls.env["account.tax"].create({
            "name": "Regression VAT 10",
            "amount": 10.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
        })
        cls.partner = cls.env["res.partner"].create({"name": "Regression Customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Regression Work",
            "type": "service",
            "list_price": 100.0,
            "taxes_id": [(6, 0, [cls.tax.id])],
        })
        cls.sale_order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.sale_line = cls.env["sale.order.line"].create({
            "order_id": cls.sale_order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
            "tax_ids": [(6, 0, [cls.tax.id])],
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

    def _income_account(self):
        account = self.product._get_product_accounts().get("income")
        if account:
            return account
        return self.env["account.account"].search([
            ("account_type", "=", "income"),
            ("company_ids", "in", self.env.company.ids),
        ], limit=1)

    def _post_credit(self, certification, lines, invoice=None):
        """Post a credit note Odoo 20 will accept.

        The original invoice is posted first. Every line has an income
        account and no tax, so price_subtotal is the price that was typed.
        """
        invoice = invoice or certification.invoice_id
        account = self._income_account()
        self.assertTrue(account)
        invoice.invoice_line_ids.write({
            "account_id": account.id,
            "tax_ids": [(6, 0, [])],
        })
        if invoice.state == "draft":
            invoice.action_post()
        prepared = []
        for line in lines:
            vals = {
                "name": line.get("name", "Credit"),
                "quantity": line["quantity"],
                "price_unit": line["price_unit"],
                "account_id": account.id,
                "tax_ids": [(6, 0, [])],
                "construction_certification_line_id": certification.line_ids.id,
                "construction_certification_id": certification.id,
            }
            if line.get("construction_adjustment_type"):
                vals["construction_adjustment_type"] = line["construction_adjustment_type"]
            prepared.append((0, 0, vals))
        refund = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": certification.partner_id.id,
            "invoice_date": "2026-06-15",
            "journal_id": invoice.journal_id.id,
            "reversed_entry_id": invoice.id,
            "invoice_line_ids": prepared,
        })
        refund.action_post()
        self.assertEqual(refund.state, "posted")
        return refund

    def _unreconcile(self, moves):
        """Drop partials and full matches so Odoo 20 will draft or reverse."""
        lines = moves.line_ids
        partials = lines.matched_debit_ids | lines.matched_credit_ids
        if partials:
            partials.unlink()
        reconciled = lines.filtered("reconciled")
        if reconciled:
            reconciled.remove_move_reconcile()
        return lines

    def _post_reversal_of_credit(self, certification, refund):
        """Post the invoice that undoes a credit note, without _reverse_moves.

        Odoo 20 may not copy construction links or may leave the reversal
        draft. This posts the same entry the filter looks for: a posted
        move whose reversed_entry_id is the credit note.
        """
        account = self._income_account()
        matched = (refund.line_ids | certification.invoice_id.line_ids).filtered("reconciled")
        if matched:
            matched.remove_move_reconcile()
        reversal = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": certification.partner_id.id,
            "invoice_date": "2026-06-16",
            "journal_id": refund.journal_id.id,
            "reversed_entry_id": refund.id,
            "invoice_line_ids": [(0, 0, {
                "name": "Reversal of credit",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": account.id,
                "tax_ids": [(6, 0, [])],
                "construction_certification_line_id": certification.line_ids.id,
                "construction_certification_id": certification.id,
            })],
        })
        reversal.action_post()
        self.assertEqual(reversal.state, "posted")
        return reversal

    # --- dependencies and computes ---------------------------------------

    def test_standard_computes_keep_odoo_20_depends(self):
        line = self.env["account.move.line"]
        price = line._fields["price_unit"].depends
        tax = line._fields["tax_ids"].depends
        quantity = line._fields["quantity"].depends
        to_invoice = self.env["sale.order.line"]._fields["qty_to_invoice"].depends
        self.assertIn("product_id", price)
        self.assertNotIn("tax_ids", price)
        self.assertIn("product_id", tax)
        self.assertNotIn("product_id.taxes_id", tax)
        self.assertNotIn("move_id.fiscal_position_id", tax)
        self.assertIn("display_type", quantity)
        self.assertIn("order_id.invoice_overages", to_invoice)

    def test_tax_compute_does_not_assign_price_unit(self):
        source = inspect.getsource(
            type(self.env["account.move.line"])._compute_tax_ids
        )
        self.assertNotIn("price_unit =", source)
        self.assertIn("add_to_compute", source)

    def test_computes_do_not_raise_usererror(self):
        line = type(self.env["account.move.line"])
        cert_line = type(self.env["construction.certification.line"])
        for method in (
            line._compute_price_unit,
            line._compute_tax_ids,
            line._compute_quantity,
            line._compute_account_id,
            cert_line._compute_origin,
            cert_line._compute_amounts,
        ):
            self.assertNotIn("UserError", inspect.getsource(method))

    def test_reversal_is_not_every_refund(self):
        source = inspect.getsource(
            type(self.env["account.move.line"])._construction_is_reversal
        )
        self.assertIn("reversed_entry_id", source)
        self.assertNotIn("out_refund", source)

    def test_partial_credit_refreshes_open_origin(self):
        source = inspect.getsource(type(self.env["account.move"]).action_post)
        self.assertIn("_recompute_open_certifications", source)

    def test_qty_invoiced_subtracts_only_still_invoiced_credits(self):
        source = inspect.getsource(
            type(self.env["sale.order.line"])._compute_qty_invoiced
        )
        self.assertIn('certification_id.state", "=", "invoiced"', source)

    def test_amount_share_uses_gross_origin(self):
        source = inspect.getsource(
            type(self.env["construction.certification.line"])._period_amount
        )
        self.assertIn("_gross_qty_origin", source)

    # --- money -----------------------------------------------------------

    def test_discount_is_removed_from_the_certified_price(self):
        self.sale_line.discount = 10.0
        cert = self._certify(1.0)
        self.assertAlmostEqual(cert.line_ids.price_unit, 90.0, places=2)

    def test_tax_included_order_is_certified_on_the_excluded_base(self):
        self.sale_order.document_tax_mode = "tax_included"
        self.sale_line.write({"price_unit": 121.0, "tax_ids": [(6, 0, [self.tax.id])]})
        cert = self._certify(1.0)
        self.assertAlmostEqual(
            cert.line_ids.price_unit, self.sale_line.price_reduce_taxexcl, places=2
        )
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        self.assertEqual(cert.invoice_id.document_tax_mode, "tax_excluded")

    def test_matching_budget_uses_the_product_tax(self):
        self.assertEqual(self._certify(1.0).line_ids._mapped_sale_taxes(), self.tax)

    def test_cleared_budget_tax_is_an_exemption(self):
        self.sale_line.tax_ids = False
        self.assertFalse(self._certify(1.0).line_ids._mapped_sale_taxes())

    def test_changed_budget_tax_is_kept(self):
        self.sale_line.tax_ids = self.other_tax
        self.assertEqual(self._certify(1.0).line_ids._mapped_sale_taxes(), self.other_tax)

    def test_absorb_stores_the_cent_and_does_not_add_it_twice(self):
        source = inspect.getsource(
            type(self.env["construction.certification"])._absorb_invoice_rounding
        )
        self.assertNotIn("price_unit +=", source)
        self.assertIn("construction_price_adjust", source)
        self.assertIn("_apply_construction_price", source)

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
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 50.0,
            "tax_ids": [(6, 0, [self.tax.id])],
        })
        advance.action_confirm()
        cert = self._certify(1.0, retention_percent=0.0, amount_advance_applied=50.0)
        cert.action_measure()
        cert.action_approve()
        with self.assertRaises(UserError):
            cert.action_create_invoice()

    # --- quantity, state, reversal ---------------------------------------

    def test_cannot_mark_invoiced_without_an_invoice(self):
        with self.assertRaises(UserError):
            self._certify(1.0).write({"state": "invoiced"})

    def test_invoice_keeps_the_measured_quantity(self):
        cert = self._certify(3.0)
        quantity, _unit = cert.line_ids._invoice_quantity_price()
        self.assertEqual(quantity, 3.0)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        product_line = cert.invoice_id.invoice_line_ids.filtered(
            lambda line: line.construction_certification_line_id
            and line.construction_adjustment_type != "rounding"
        )
        self.assertEqual(product_line.quantity, 3.0)

    def test_reversal_copy_keeps_the_construction_links(self):
        cert = self._certify(1.0)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        product_line = cert.invoice_id.invoice_line_ids.filtered(
            "construction_certification_line_id"
        )[:1]
        copied = product_line.with_context(construction_keep_links=True).copy_data()[0]
        self.assertEqual(
            copied["construction_certification_line_id"],
            product_line.construction_certification_line_id.id,
        )
        self.assertEqual(copied["price_unit"], product_line.price_unit)
        self.assertEqual(copied["quantity"], product_line.quantity)

    def test_origin_quantity_matches_the_origin_amount(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        later = self._certify(1.0, date="2026-07-01")
        self.assertEqual(later.line_ids.qty_origin, 5.0)
        self.assertAlmostEqual(later.line_ids.amount_origin, 500.0, places=2)

    def test_negative_credit_quantity_still_reduces_the_net_origin(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        # Odoo 20 rejects a negative quantity on an invoice line. Post a
        # positive one, then store -1 the way a reversal can leave it.
        refund = self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        credit_line = refund.invoice_line_ids.filtered(
            "construction_certification_line_id"
        )
        self.env.cr.execute(
            "UPDATE account_move_line SET quantity = %s WHERE id = %s",
            [-1.0, credit_line.id],
        )
        credit_line.invalidate_recordset()
        first.line_ids._compute_origin()
        first.line_ids._compute_amounts()
        later = self._certify(1.0, date="2026-07-01")
        self.assertEqual(later.line_ids.qty_origin, 5.0)
        self.assertEqual(later.line_ids.qty_origin_net, 4.0)
        self.assertAlmostEqual(first.line_ids.amount_origin_net, 300.0, places=2)

    def test_reversing_the_credit_note_does_not_count_as_another_credit(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        refund = self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        first.invalidate_recordset()
        self.assertEqual(first.line_ids.qty_origin_net, 3.0)
        self._unreconcile(refund | first.invoice_id)
        reversal = refund.with_context(construction_keep_links=True)._reverse_moves(
            default_values_list=[{"invoice_date": "2026-06-16"}],
            cancel=False,
        )
        reversal.filtered(lambda move: move.state == "draft").action_post()
        self.assertTrue(reversal)
        self.assertEqual(reversal[:1].state, "posted")
        self.assertTrue(
            reversal[:1].reversed_entry_id == refund
            or reversal[:1] in refund.reversal_move_ids
        )
        first.invalidate_recordset()
        self.assertEqual(first.line_ids.qty_origin_net, 4.0)
        self.assertAlmostEqual(first.line_ids.amount_origin_net, 400.0, places=2)

    def test_positive_credit_quantity_reduces_the_net_origin(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        later = self._certify(1.0, date="2026-07-01")
        self.assertEqual(later.line_ids.qty_origin_net, 4.0)

    def test_open_origin_refreshes_when_a_credit_is_posted(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        later = self._certify(1.0, date="2026-07-01")
        self.assertEqual(later.line_ids.qty_origin_net, 5.0)
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        later.invalidate_recordset()
        self.assertEqual(later.line_ids.qty_origin, 5.0)
        self.assertEqual(later.line_ids.qty_origin_net, 4.0)

    def test_invoiced_billed_row_stays_and_net_row_moves_together(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        first.invalidate_recordset()
        line = first.line_ids
        self.assertEqual(line.qty_origin, 4.0)
        self.assertAlmostEqual(line.percent_origin, 0.4, places=4)
        self.assertEqual(line.amount_origin, 400.0)
        self.assertEqual(line.qty_origin_net, 3.0)
        self.assertAlmostEqual(line.percent_origin_net, 0.3, places=4)
        self.assertAlmostEqual(line.amount_origin_net, 300.0, places=2)

    def test_changing_a_posted_credit_quantity_refreshes_the_open_origin(self):
        first = self._certify(4.0, date="2026-06-01")
        invoice = mark_invoiced(first)
        later = self._certify(1.0, date="2026-07-01")
        refund = self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}], invoice)
        self._unreconcile(refund | invoice)
        self.assertFalse((refund.line_ids | invoice.line_ids).matched_debit_ids)
        self.assertFalse((refund.line_ids | invoice.line_ids).matched_credit_ids)
        refund.button_draft()
        refund.invoice_line_ids.filtered(
            "construction_certification_line_id"
        ).quantity = 2.0
        refund.action_post()
        later.invalidate_recordset()
        first.invalidate_recordset()
        self.assertEqual(later.line_ids.qty_origin_net, 3.0)
        self.assertEqual(first.line_ids.qty_origin_net, 2.0)

    def test_posted_write_refreshes_origin_without_action_post(self):
        source = inspect.getsource(type(self.env["account.move"]).write)
        self.assertIn("_refresh_open_construction_origins", source)
        line_source = inspect.getsource(type(self.env["account.move.line"]).write)
        self.assertIn("_refresh_open_construction_origins", line_source)

    def test_open_net_row_matches_the_billed_row_without_a_credit(self):
        cert = self._certify(4.0)
        line = cert.line_ids
        self.assertEqual(line.qty_origin, line.qty_origin_net)
        self.assertAlmostEqual(line.percent_origin, line.percent_origin_net, places=4)
        self.assertAlmostEqual(line.amount_origin, line.amount_origin_net, places=2)

    def test_net_origin_does_not_go_below_zero(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self._post_credit(first, [{"quantity": 9.0, "price_unit": 100.0}])
        first.invalidate_recordset()
        self.assertEqual(first.line_ids.qty_origin, 4.0)
        self.assertEqual(first.line_ids.qty_origin_net, 0.0)
        self.assertEqual(first.line_ids.percent_origin_net, 0.0)
        self.assertEqual(first.line_ids.amount_origin_net, 0.0)

    def test_net_amount_is_the_credit_note_not_a_share(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self.sale_line.price_unit = 50.0
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 80.0}])
        first.invalidate_recordset()
        self.assertEqual(first.line_ids.amount_origin, 400.0)
        self.assertAlmostEqual(first.line_ids.amount_origin_net, 320.0, places=2)

    def test_two_partial_credits_add_up(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        self._post_credit(first, [{"quantity": 1.5, "price_unit": 100.0}])
        first.invalidate_recordset()
        self.assertEqual(first.line_ids.qty_origin, 4.0)
        self.assertEqual(first.line_ids.qty_origin_net, 1.5)
        self.assertAlmostEqual(first.line_ids.amount_origin, 400.0, places=2)
        self.assertAlmostEqual(first.line_ids.amount_origin_net, 150.0, places=2)
        self.assertEqual(first.state, "invoiced")
        self.assertTrue(first.invoice_id)

    def test_second_partial_credit_refreshes_the_open_origin(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        later = self._certify(1.0, date="2026-07-01")
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        later.invalidate_recordset()
        self.assertEqual(later.line_ids.qty_origin_net, 4.0)
        self._post_credit(first, [{"quantity": 0.5, "price_unit": 80.0}])
        later.invalidate_recordset()
        first.invalidate_recordset()
        self.assertEqual(later.line_ids.qty_origin, 5.0)
        self.assertEqual(later.line_ids.qty_origin_net, 3.5)
        self.assertAlmostEqual(first.line_ids.amount_origin_net, 260.0, places=2)

    def test_header_net_origin_moves_with_the_credit(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self.assertAlmostEqual(first.amount_certified_origin, 400.0, places=2)
        self._post_credit(first, [{"quantity": 1.0, "price_unit": 100.0}])
        first.invalidate_recordset()
        first._compute_amounts()
        self.assertAlmostEqual(first.amount_certified_origin, 400.0, places=2)
        self.assertAlmostEqual(first.amount_certified_origin_net, 300.0, places=2)

    def test_full_credit_keeps_the_header_net_at_zero(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self._post_credit(first, [{"quantity": 4.0, "price_unit": 100.0}])
        first.invalidate_recordset()
        first._compute_amounts()
        self.assertAlmostEqual(first.amount_certified_origin, 400.0, places=2)
        self.assertEqual(first.amount_certified_origin_net, 0.0)

    def test_credited_advance_deduction_frees_the_pending_balance(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 100.0,
            "tax_ids": [(6, 0, [])],
        })
        advance.action_confirm()
        first = self._certify(1.0, date="2026-06-01", retention_percent=0.0)
        first.write({"application_ids": [(0, 0, {"advance_id": advance.id, "amount": 100.0})]})
        mark_invoiced(first)
        self.assertEqual(advance.amount_pending, 0.0)
        invoice = first.invoice_id
        account = self._income_account()
        refund = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": first.partner_id.id,
            "invoice_date": "2026-06-15",
            "journal_id": invoice.journal_id.id,
            "reversed_entry_id": invoice.id,
            "invoice_line_ids": [(0, 0, {
                "name": "Advance returned",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": account.id,
                "tax_ids": [(6, 0, [])],
                "construction_advance_application_id": first.application_ids.id,
                "construction_adjustment_type": "advance",
            })],
        })
        refund.action_post()
        advance.invalidate_recordset()
        self.assertAlmostEqual(advance.amount_pending, 100.0, places=2)
        later = self._certify(1.0, date="2026-07-01", retention_percent=0.0)
        later.amount_advance_applied = 100.0
        self.assertEqual(later.application_ids.advance_id, advance)
        self.assertAlmostEqual(later.application_ids.amount, 100.0, places=2)

    def test_credited_retention_is_not_still_held(self):
        first = self._certify(4.0, date="2026-06-01", retention_percent=5.0)
        mark_invoiced(first)
        later = self._certify(0.0, date="2026-07-01", is_retention_liquidation=True)
        self.assertAlmostEqual(later._retention_held_from_previous(), 20.0, places=2)
        invoice = first.invoice_id
        account = self._income_account()
        self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": first.partner_id.id,
            "invoice_date": "2026-06-15",
            "journal_id": invoice.journal_id.id,
            "reversed_entry_id": invoice.id,
            "invoice_line_ids": [(0, 0, {
                "name": "Retention returned",
                "quantity": 1.0,
                "price_unit": 20.0,
                "account_id": account.id,
                "tax_ids": [(6, 0, [])],
                "construction_certification_id": first.id,
                "construction_adjustment_type": "retention",
            })],
        }).action_post()
        self.assertAlmostEqual(later._retention_held_from_previous(), 0.0, places=2)

    def test_retention_percent_can_differ_from_the_default(self):
        default = self._certify(4.0)
        self.assertEqual(default.retention_percent, 5.0)
        self.assertAlmostEqual(default.amount_retention, 20.0, places=2)
        self.assertAlmostEqual(default.amount_net_to_invoice, 380.0, places=2)
        changed = self._certify(4.0, date="2026-07-01", retention_percent=10.0)
        self.assertEqual(changed.retention_percent, 10.0)
        self.assertAlmostEqual(changed.amount_to_invoice, 400.0, places=2)
        self.assertAlmostEqual(changed.amount_retention, 40.0, places=2)
        self.assertAlmostEqual(changed.amount_net_to_invoice, 360.0, places=2)
        changed.retention_percent = 0.0
        self.assertEqual(changed.amount_retention, 0.0)
        self.assertAlmostEqual(changed.amount_net_to_invoice, 400.0, places=2)
        changed.retention_percent = 2.5
        self.assertAlmostEqual(changed.amount_retention, 10.0, places=2)

    def test_company_construction_accounts_are_required_and_reconcilable(self):
        company = self.env.company
        advance = company.construction_advance_account_id
        retention = company.construction_retention_account_id
        self.assertTrue(advance)
        self.assertTrue(retention)
        self.assertEqual(advance.account_type, "liability_current")
        self.assertEqual(retention.account_type, "asset_current")
        self.assertIn(company, advance.company_ids)
        self.assertIn(company, retention.company_ids)
        self.assertTrue(advance.reconcile)
        self.assertTrue(retention.reconcile)
        form = self.env.ref("tl_construction_certification.view_company_form_construction_certification")
        self.assertIn("construction_advance_account_id", form.arch)
        self.assertIn("construction_retention_account_id", form.arch)
        company.construction_advance_account_id = False
        with self.assertRaises(UserError):
            company._get_construction_advance_account()
        advance_doc = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 100.0,
        })
        advance_doc.action_confirm()
        with self.assertRaises(UserError):
            advance_doc.action_create_invoice()
        company.construction_advance_account_id = advance
        retained = self._certify(1.0, date="2026-06-01", retention_percent=10.0)
        retained.action_measure()
        retained.action_approve()
        retained.action_create_invoice()
        retained.invoice_id.action_post()
        company.construction_retention_account_id = False
        cert = self._certify(1.0, date="2026-07-01", retention_percent=5.0)
        cert.action_measure()
        cert.action_approve()
        with self.assertRaises(UserError):
            cert.action_create_invoice()
        liquidation = self._certify(
            0.0, date="2026-08-01", is_retention_liquidation=True, retention_to_release=10.0,
        )
        liquidation.action_measure()
        liquidation.action_approve()
        with self.assertRaises(UserError):
            liquidation.action_create_invoice()
        company.construction_retention_account_id = retention
        other = self.env["res.company"].create({"name": "Other construction company"})
        foreign = self.env["account.account"].create({
            "name": "Foreign retention",
            "code": "560099",
            "account_type": "asset_current",
            "reconcile": True,
            "company_ids": [(6, 0, [other.id])],
        })
        with self.env.cr.savepoint(), self.assertRaises(ValidationError):
            company.construction_retention_account_id = foreign
        plain = self.env["account.account"].create({
            "name": "Not reconcilable",
            "code": "560098",
            "account_type": "asset_current",
            "reconcile": False,
            "company_ids": [(6, 0, [company.id])],
        })
        company.construction_retention_account_id = plain
        with self.assertRaises(UserError):
            company._get_construction_retention_account()
        company.construction_retention_account_id = retention

    def test_company_rejects_an_account_from_another_company(self):
        company = self.env.company
        other = self.env["res.company"].create({"name": "Foreign books"})
        foreign = self.env["account.account"].create({
            "name": "Foreign advance",
            "code": "438099",
            "account_type": "liability_current",
            "reconcile": True,
            "company_ids": [(6, 0, [other.id])],
        })
        with self.assertRaises(ValidationError):
            company.construction_advance_account_id = foreign

    def test_deducting_an_advance_requires_the_advance_account(self):
        company = self.env.company
        advance_account = company.construction_advance_account_id
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 50.0,
        })
        advance.action_confirm()
        advance.action_create_invoice()
        advance.invoice_id.action_post()
        cert = self._certify(1.0, retention_percent=0.0)
        cert.write({"application_ids": [(0, 0, {"advance_id": advance.id, "amount": 50.0})]})
        cert.action_measure()
        cert.action_approve()
        company.construction_advance_account_id = False
        with self.assertRaises(UserError):
            cert.action_create_invoice()
        company.construction_advance_account_id = advance_account

    def test_invoices_use_the_company_construction_accounts(self):
        company = self.env.company
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 100.0,
        })
        advance.action_confirm()
        advance.action_create_invoice()
        self.assertEqual(
            advance.invoice_id.invoice_line_ids.account_id,
            company.construction_advance_account_id,
        )
        cert = self._certify(1.0, date="2026-07-01", retention_percent=5.0)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        retention = cert.invoice_id.invoice_line_ids.filtered(
            lambda line: line.construction_adjustment_type == "retention"
        )
        self.assertEqual(retention.account_id, company.construction_retention_account_id)

    def test_confirmed_order_with_a_project_can_be_certified(self):
        self.assertEqual(self.sale_order.state, "sale")
        project = self.env["project.project"].create({"name": "Site"})
        if "project_id" in self.sale_order._fields:
            self.sale_order.project_id = project
        wizard = self.env["create.certification.wizard"].create({
            "sale_order_id": self.sale_order.id,
            "date": "2026-06-01",
            "import_from_progress": False,
        })
        action = wizard.action_create_certification()
        cert = self.env["construction.certification"].browse(action["res_id"])
        self.assertEqual(cert.sale_order_id, self.sale_order)
        self.assertEqual(cert.partner_id, self.partner)
        if "project_id" in self.sale_order._fields:
            self.assertEqual(cert.project_id, project)
        self.assertEqual(cert.state, "draft")

    def test_create_certification_button_opens_the_wizard(self):
        view = self.env.ref("tl_construction_certification.view_sale_order_form_certification")
        self.assertIn("Create Certification", view.arch)
        self.assertIn("state not in ('sale', 'done')", view.arch)
        action = self.env.ref("tl_construction_certification.action_create_certification_wizard")
        self.assertEqual(action.res_model, "create.certification.wizard")
        wizard = self.env["create.certification.wizard"].with_context(
            active_id=self.sale_order.id,
            active_model="sale.order",
        ).create({"sale_order_id": self.sale_order.id})
        result = wizard.action_create_certification()
        self.assertEqual(result["res_model"], "construction.certification")
        self.assertEqual(result["view_mode"], "form")

    def test_wizard_uses_the_date_and_the_progress_choice(self):
        wizard = self.env["create.certification.wizard"].create({
            "sale_order_id": self.sale_order.id,
            "date": "2026-08-15",
            "import_from_progress": False,
        })
        cert = self.env["construction.certification"].browse(
            wizard.action_create_certification()["res_id"]
        )
        self.assertEqual(str(cert.date), "2026-08-15")
        self.assertEqual(cert.line_ids.qty_period, 0.0)
        source = inspect.getsource(
            type(self.env["create.certification.wizard"]).action_create_certification
        )
        self.assertIn("x_cumulated_qty", source)
        self.assertIn("import_from_progress", source)
        importing = self.env["create.certification.wizard"].create({
            "sale_order_id": self.sale_order.id,
            "date": "2026-08-16",
            "import_from_progress": True,
        })
        imported = self.env["construction.certification"].browse(
            importing.action_create_certification()["res_id"]
        )
        self.assertEqual(str(imported.date), "2026-08-16")
        if "x_production_ids" not in self.sale_line._fields:
            self.assertEqual(imported.line_ids.qty_period, 0.0)

    def test_period_quantity_and_percent_stay_aligned(self):
        cert = self._certify(2.0)
        line = cert.line_ids
        self.assertAlmostEqual(line.percent_period, 0.2, places=4)
        line.qty_period = 4.0
        self.assertAlmostEqual(line.percent_period, 0.4, places=4)
        line.percent_period = 0.5
        self.assertAlmostEqual(line.qty_period, 5.0, places=4)
        view = self.env.ref("tl_construction_certification.view_construction_certification_form")
        self.assertIn('name="mrp_cumulated_qty"', view.arch)
        self.assertIn('name="mrp_cumulated_percent"', view.arch)
        self.assertIn('name="qty_period"', view.arch)
        self.assertIn('name="percent_period"', view.arch)
        self.assertEqual(line.mrp_cumulated_qty, 0.0)
        line.qty_period = 3.0
        self.assertEqual(line.mrp_cumulated_qty, 0.0)

    def test_apply_pending_advance_adds_without_moving_chosen_lines(self):
        first = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 300.0,
            "date": "2026-01-01",
        })
        second = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 200.0,
            "date": "2026-02-01",
        })
        (first | second).action_confirm()
        cert = self._certify(4.0)
        cert.write({
            "application_ids": [(0, 0, {"advance_id": second.id, "amount": 50.0})],
        })
        kept = cert.application_ids
        cert.action_apply_advance()
        by_advance = {app.advance_id: app.amount for app in cert.application_ids}
        self.assertEqual(by_advance[second], 50.0)
        self.assertEqual(
            cert.application_ids.filtered(lambda app: app.advance_id == second),
            kept,
        )
        self.assertEqual(cert.amount_advance_applied, min(cert.amount_net_to_invoice, 500.0))
        cert.amount_advance_applied = 80.0
        self.assertEqual(
            cert.application_ids.filtered(lambda app: app.advance_id == second).amount,
            50.0,
        )
        self.assertEqual(sum(cert.application_ids.mapped("amount")), 80.0)

    def test_lowering_the_advance_total_takes_from_the_newest(self):
        first = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 300.0,
            "date": "2026-01-01",
            "tax_ids": [(6, 0, [])],
        })
        second = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 200.0,
            "date": "2026-02-01",
            "tax_ids": [(6, 0, [])],
        })
        (first | second).action_confirm()
        cert = self._certify(4.0, retention_percent=0.0)
        cert.amount_advance_applied = 400.0
        cert.amount_advance_applied = 250.0
        by_advance = {app.advance_id: app.amount for app in cert.application_ids}
        self.assertEqual(by_advance.get(first), 250.0)
        self.assertNotIn(second, by_advance)
        self.assertEqual(second.amount_pending, 200.0)

    def test_apply_pending_advance_stops_at_the_net_amount(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 1000.0,
            "tax_ids": [(6, 0, [])],
        })
        advance.action_confirm()
        cert = self._certify(4.0, retention_percent=5.0)
        cert.action_apply_advance()
        self.assertAlmostEqual(cert.amount_advance_applied, cert.amount_net_to_invoice, places=2)
        self.assertLess(cert.amount_advance_applied, 1000.0)
        cert.amount_advance_applied = cert.amount_net_to_invoice + 50.0
        with self.assertRaises(UserError):
            cert.action_apply_advance()
        cert.action_approve()
        with self.assertRaises(UserError):
            cert.action_apply_advance()

    def test_advance_deduction_reverses_the_excluded_base_taxes(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 50.0,
            "tax_ids": [(6, 0, [self.tax.id])],
        })
        advance.action_confirm()
        advance.action_create_invoice()
        self.assertEqual(advance.invoice_id.document_tax_mode, "tax_excluded")
        self.assertEqual(advance.invoice_id.invoice_line_ids.price_unit, 50.0)
        self.assertEqual(advance.invoice_id.invoice_line_ids.tax_ids, self.tax)
        advance.invoice_id.action_post()
        cert = self._certify(1.0, date="2026-07-01", retention_percent=0.0)
        cert.write({"application_ids": [(0, 0, {"advance_id": advance.id, "amount": 50.0})]})
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        deduction = cert.invoice_id.invoice_line_ids.filtered(
            lambda line: line.construction_adjustment_type == "advance"
        )
        self.assertEqual(deduction.price_unit, -50.0)
        self.assertEqual(deduction.tax_ids, self.tax)
        self.assertEqual(cert.invoice_id.document_tax_mode, "tax_excluded")

    def test_rounding_cent_enters_the_net_amount_not_the_quantity(self):
        first = self._certify(4.0, date="2026-06-01")
        mark_invoiced(first)
        self._post_credit(first, [
            {"quantity": 1.0, "price_unit": 80.0},
            {
                "name": "Rounding",
                "quantity": 1.0,
                "price_unit": 0.01,
                "construction_adjustment_type": "rounding",
            },
        ])
        first.invalidate_recordset()
        self.assertEqual(first.line_ids.qty_origin_net, 3.0)
        self.assertAlmostEqual(first.line_ids.amount_origin_net, 319.99, places=2)

    def test_net_amount_is_computed_with_the_amounts(self):
        source = inspect.getsource(
            type(self.env["construction.certification.line"])._compute_amounts
        )
        origin = inspect.getsource(
            type(self.env["construction.certification.line"])._compute_origin
        )
        self.assertIn("amount_origin_net", source)
        self.assertNotIn("amount_origin_net", origin)

    def test_form_keeps_the_billed_row_apart_from_the_net_row(self):
        view = self.env.ref("tl_construction_certification.view_construction_certification_form")
        arch = view.arch
        billed = arch.index('name="amount_origin"')
        net_qty = arch.index('name="qty_origin_net"')
        self.assertLess(billed, net_qty)
        self.assertEqual(arch.count('name="amount_origin"'), 1)

    def test_deleting_a_certification_does_not_reuse_its_number(self):
        first = self._certify(1.0)
        number = first.certification_number
        first.unlink()
        second = self._certify(1.0)
        self.assertNotEqual(second.certification_number, number)

    def test_invoice_uses_the_company_construction_accounts(self):
        cert = self._certify(1.0, retention_percent=5.0)
        cert.action_measure()
        cert.action_approve()
        cert.action_create_invoice()
        retention = cert.invoice_id.invoice_line_ids.filtered(
            lambda line: line.construction_adjustment_type == "retention"
        )
        self.assertEqual(
            retention.account_id,
            self.env.company.construction_retention_account_id,
        )
