# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import float_round
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestCriticalConstructionFixes(TransactionCase):
    """Financial invariants missing from the previous regression suite."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_construction_accounts(cls.env)
        cls.partner = cls.env["res.partner"].create({"name": "Construction QA"})
        cls.product = cls.env["product.product"].create({
            "name": "Certified Work",
            "type": "service",
            "invoice_policy": "order",
            "list_price": 100.0,
        })
        cls.order = cls.env["sale.order"].create({"partner_id": cls.partner.id})
        cls.sale_a = cls.env["sale.order.line"].create({
            "order_id": cls.order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
            "tax_ids": [(6, 0, [])],
        })
        cls.sale_b = cls.env["sale.order.line"].create({
            "order_id": cls.order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 50.0,
            "tax_ids": [(6, 0, [])],
        })
        cls.order.action_confirm()

    def test_empty_certification_cannot_be_approved_even_via_rpc(self):
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.order.id, "date": "2026-06-01",
        })
        with self.assertRaises(UserError):
            cert.action_approve()
        with self.assertRaises(UserError):
            cert.write({"state": "approved"})
        with self.assertRaises(UserError):
            cert.write({"state": "measured"})

    def test_discount_contract_line_is_in_origin_invoice(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        work = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "product_uom_qty": 10.0, "price_unit": 100.0,
            "tax_ids": [(6, 0, [])],
        })
        discount = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "product_uom_qty": 1.0, "price_unit": -100.0,
            "tax_ids": [(6, 0, [])],
        })
        order.action_confirm()
        cert = self.env["construction.certification"].create({
            "sale_order_id": order.id, "retention_percent": 0.0,
            "date": "2026-06-01",
        })
        Line = self.env["construction.certification.line"]
        Line.create({"certification_id": cert.id, "sale_line_id": work.id, "qty_period": 5.0})
        off = Line.create({
            "certification_id": cert.id, "sale_line_id": discount.id, "qty_period": 0.5,
        })
        self.assertAlmostEqual(off.amount_period, -50.0)
        self.assertAlmostEqual(off.amount_origin_net, -50.0)
        self.assertAlmostEqual(cert.amount_to_invoice, 450.0)
        invoice_values = cert._prepare_invoice_vals()
        entries = [row[2] for row in invoice_values["invoice_line_ids"]
                   if row[2].get("construction_certification_line_id")]
        self.assertTrue(any(row["price_unit"] < 0 for row in entries))
        self.assertAlmostEqual(sum(
            row["price_unit"] * row["quantity"] for row in entries
        ), 450.0, places=2)

    def test_last_cent_of_negative_contract_coefficient_is_preserved(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        negative = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "product_uom_qty": 1.0, "price_unit": -100.01,
            "tax_ids": [(6, 0, [])],
        })
        positive = self.env["sale.order.line"].create({
            "order_id": order.id, "product_id": self.product.id,
            "product_uom_qty": 1.0, "price_unit": 200.0,
            "tax_ids": [(6, 0, [])],
        })
        order.action_confirm()
        # Odoo 20 rounds fields.Float on assignment according to the decimal
        # precision configured on the field.  The old test always passed four
        # decimals even when Product Unit of Measure allowed only two: each
        # 0.3333 / 0.3334 was stored as 0.33, so only 0.99 was certified.
        # Use representable quantities and put the remaining quantity into
        # the last period; this checks the final cent at ANY configured scale.
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        self.assertGreaterEqual(precision, 1)
        first_qty = float_round(1.0 / 3.0, precision_digits=precision)
        last_qty = float_round(1.0 - 2.0 * first_qty, precision_digits=precision)
        self.assertAlmostEqual(2 * first_qty + last_qty, 1.0, places=precision)
        periods = []
        for date_value, quantity in (
            ("2026-06-01", first_qty),
            ("2026-07-01", first_qty),
            ("2026-08-01", last_qty),
        ):
            cert = self.env["construction.certification"].create({
                "sale_order_id": order.id,
                "date": date_value,
                "retention_percent": 0.0,
            })
            self.env["construction.certification.line"].create({
                "certification_id": cert.id, "sale_line_id": positive.id,
                "qty_period": quantity,
            })
            debit = self.env["construction.certification.line"].create({
                "certification_id": cert.id, "sale_line_id": negative.id,
                "qty_period": quantity,
            })
            self.assertAlmostEqual(debit.qty_period, quantity, places=precision)
            periods.append(debit.amount_period)
            cert.action_approve()
        self.assertAlmostEqual(sum(periods), -100.01, places=2)
        # The engine rounds the cumulative origin, not each isolated period.
        # Therefore the last period is the remaining rounded contract amount:
        # e.g. -34.00 for 2-decimal quantities, -33.34 for 4-decimal quantities.
        currency = order.currency_id
        previous_cumulative = currency.round(-100.01 * (2.0 * first_qty))
        expected_last = currency.round(-100.01 - previous_cumulative)
        self.assertAlmostEqual(periods[-1], expected_last, places=2)

    def _certify(self, sale_line=None, qty=1.0, date="2026-06-01", retention=0.0):
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.order.id,
            "date": date,
            "retention_percent": retention,
        })
        if sale_line:
            self.env["construction.certification.line"].create({
                "certification_id": cert.id,
                "sale_line_id": sale_line.id,
                "qty_period": qty,
            })
        return cert

    def _approve(self, cert):
        cert.action_measure()
        cert.action_approve()
        return cert

    def _advance(self, amount=100.0, post=False):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.order.id,
            "amount": amount,
            "tax_ids": [(6, 0, [])],
        })
        advance.action_confirm()
        if post:
            advance.action_create_invoice()
            advance.invoice_id.action_post()
        return advance

    def _partial_credit(self, cert, quantity, price=100.0, extra=None):
        invoice = cert.invoice_id
        if invoice.state == "draft":
            invoice.action_post()
        source = invoice.invoice_line_ids.filtered(
            lambda line: bool(line.construction_certification_line_id)
            and not line.construction_adjustment_type
        )[:1]
        values = {
            "name": "Partial work refund",
            "quantity": quantity,
            "price_unit": price,
            "account_id": source.account_id.id,
            "tax_ids": [(6, 0, source.tax_ids.ids)],
            "construction_certification_id": cert.id,
            "construction_certification_line_id": source.construction_certification_line_id.id,
        }
        note = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": invoice.partner_id.id,
            "company_id": invoice.company_id.id,
            "invoice_date": "2026-06-15",
            "journal_id": invoice.journal_id.id,
            "reversed_entry_id": invoice.id,
            "invoice_line_ids": [(0, 0, values)] + (extra or []),
        })
        note.action_post()
        return note

    def test_cumulative_mrp_values_are_not_summed_for_multiple_orders(self):
        from types import SimpleNamespace

        class Productions:
            _fields = {"x_cumulated_qty": True}

            def mapped(self, field):
                self.called = field
                return [20.0, 20.0]

        productions = Productions()
        sale_line = SimpleNamespace(
            _fields={"x_production_ids": True},
            x_production_ids=productions,
            product_uom_qty=40.0,
        )
        qty, percent = self.env["construction.certification.line"]._sale_line_mrp_progress(sale_line)
        self.assertEqual(qty, 20.0)
        self.assertEqual(percent, 0.5)

    def test_selected_lines_keep_previous_origin(self):
        first = self._approve(self._certify(self.sale_a, 3))
        second = self._certify(self.sale_b, 2, date="2026-07-01")
        self.assertAlmostEqual(first.amount_to_invoice, 300.0, places=2)
        self.assertAlmostEqual(second.amount_to_invoice, 100.0, places=2)
        self.assertAlmostEqual(second.amount_certified_origin, 400.0, places=2)
        self.assertAlmostEqual(second.amount_certified_origin_net, 400.0, places=2)

    def test_zero_net_with_posted_advance_still_generates_invoice(self):
        advance = self._advance(post=True)
        cert = self._certify(self.sale_a)
        cert.application_ids = [(0, 0, {"advance_id": advance.id, "amount": 100.0})]
        self._approve(cert)
        self.assertTrue(cert.currency_id.is_zero(cert.amount_final_to_invoice))
        cert.action_create_invoice()
        self.assertEqual(cert.state, "invoiced")
        self.assertAlmostEqual(cert.invoice_id.amount_untaxed, 0.0, places=2)
        self.assertEqual(len(cert.invoice_id.invoice_line_ids.filtered("construction_advance_application_id")), 1)

    def test_untaxed_advance_requires_posted_invoice(self):
        advance = self._advance()
        cert = self._certify(self.sale_a)
        cert.application_ids = [(0, 0, {"advance_id": advance.id, "amount": 100.0})]
        self._approve(cert)
        with self.assertRaises(UserError):
            cert.action_create_invoice()

    def test_confirmed_advance_cannot_be_changed_or_deleted(self):
        advance = self._advance()
        with self.assertRaises(UserError):
            advance.write({"amount": 120.0})
        with self.assertRaises(UserError):
            advance.write({"tax_ids": [(6, 0, [])]})
        with self.assertRaises(UserError):
            advance.action_confirm()
        with self.assertRaises(UserError):
            advance.unlink()

    def test_cannot_change_certification_state_through_rpc_without_reversal(self):
        cert = self._approve(self._certify(self.sale_a))
        cert.action_create_invoice()
        cert.invoice_id.action_post()
        with self.assertRaises(UserError):
            cert.write({"state": "cancel"})
        with self.assertRaises(UserError):
            cert.write({"invoice_id": False})
        self.assertEqual(cert.state, "invoiced")

    def test_partial_credit_blocks_cancel_until_remaining_is_refunded(self):
        cert = self._approve(self._certify(self.sale_a, 4))
        cert.action_create_invoice()
        self._partial_credit(cert, 1)
        self.assertEqual(cert.state, "invoiced")
        with self.assertRaises(UserError):
            cert.action_cancel()
        self._partial_credit(cert, 3)
        self.assertEqual(cert.state, "cancel")
        self.assertTrue(cert.invoice_id._construction_reversal_is_complete(cert.invoice_id))

    def test_refunding_work_only_does_not_cancel_withheld_retention(self):
        cert = self._approve(self._certify(self.sale_a, 4, retention=5.0))
        cert.action_create_invoice()
        self._partial_credit(cert, 4)
        self.assertEqual(cert.state, "invoiced")
        with self.assertRaises(UserError):
            cert.action_cancel()

    def test_reversed_credit_restores_invoiced_state(self):
        cert = self._approve(self._certify(self.sale_a, 2))
        cert.action_create_invoice()
        cert.invoice_id.action_post()
        refund = cert.invoice_id._reverse_moves(cancel=False)
        refund.action_post()
        self.assertEqual(cert.state, "cancel")
        # The credit reversal restores the original invoice's net effect.
        undo = refund._reverse_moves(cancel=False)
        undo.action_post()
        self.assertEqual(cert.state, "invoiced")
        self.assertFalse(cert.reversal_invoice_id)

    def test_billed_snapshot_survives_full_refund_and_budget_repricing(self):
        cert = self._approve(self._certify(self.sale_a, 2))
        cert.action_create_invoice()
        cert.invoice_id.action_post()
        original = cert.amount_to_invoice
        refund = cert.invoice_id._reverse_moves(cancel=False)
        refund.action_post()
        self.assertEqual(cert.state, "cancel")
        self.sale_a.price_unit = 200.0
        cert.line_ids._compute_origin()
        cert.line_ids._compute_amounts()
        cert._compute_amounts()
        self.assertAlmostEqual(cert.amount_to_invoice, original, places=2)
        self.assertAlmostEqual(cert.amount_certified_origin, original, places=2)
        self.assertAlmostEqual(cert.amount_certified_origin_net, 0.0, places=2)

    def test_credit_frees_wizard_budget_without_double_mrp(self):
        cert = self._approve(self._certify(self.sale_a, 10))
        cert.action_create_invoice()
        self._partial_credit(cert, 4)
        self.assertEqual(cert.state, "invoiced")
        Model = type(self.env["construction.certification.line"])

        def progress(_model, sale_line):
            return (10.0, 1.0) if sale_line == self.sale_a else (0.0, 0.0)

        with patch.object(Model, "_sale_line_mrp_progress", progress):
            wizard = self.env["create.certification.wizard"].create({
                "sale_order_id": self.order.id,
                "date": "2026-07-01",
                "import_from_progress": True,
            })
            action = wizard.action_create_certification()
        new_cert = self.env["construction.certification"].browse(action["res_id"])
        self.assertAlmostEqual(
            new_cert.line_ids.filtered(lambda line: line.sale_line_id == self.sale_a).qty_period,
            4.0, places=2,
        )

    def test_cancelled_draft_invoice_is_no_longer_certified(self):
        cert = self._approve(self._certify(self.sale_a, 3))
        cert.action_create_invoice()
        cert.invoice_id.button_cancel()
        self.assertEqual(cert.state, "cancel")
        self.sale_a.invalidate_recordset(["qty_invoiced"])
        self.assertAlmostEqual(self.sale_a.qty_invoiced, 0.0, places=2)

    def test_writes_reject_wrong_accounting_types(self):
        wrong = self.env["account.account"].create({
            "name": "Wrong retention type",
            "code": "123698",
            "account_type": "liability_current",
            "company_ids": [(6, 0, [self.env.company.id])],
            "reconcile": True,
        })
        with self.assertRaises(ValidationError):
            self.env.company.construction_retention_account_id = wrong
