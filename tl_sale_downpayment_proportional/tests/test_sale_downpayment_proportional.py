# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Integration tests for native Odoo 20 advance *invoices*."""

from odoo.fields import Command
from odoo.tests import tagged
from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestSaleDownpaymentProportional(TestSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dp_customer = cls.env["res.partner"].create({"name": "DP Test Customer"})
        cls.dp_product = cls.env["product.product"].create(
            {
                "name": "Partially invoiced service",
                "type": "service",
                "invoice_policy": "delivery",
                "list_price": 1000.0,
                "taxes_id": [Command.clear()],
            }
        )

    def _make_order(self, taxes=None, partner=None):
        taxes = taxes or self.env["account.tax"]
        order = self.env["sale.order"].create(
            {
                "partner_id": (partner or self.dp_customer).id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": self.dp_product.id,
                            "name": "Partial delivery",
                            "product_uom_qty": 10,
                            "price_unit": 1000,
                            "tax_ids": [Command.set(taxes.ids)],
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        return order

    def _make_advance(self, order, percent=30, fixed=None):
        vals = {
            "sale_order_ids": [Command.set(order.ids)],
            "advance_payment_method": "fixed" if fixed is not None else "percentage",
        }
        if fixed is None:
            vals["amount"] = percent
        else:
            vals["fixed_amount"] = fixed
        return self.env["sale.advance.payment.inv"].create(vals)._create_invoices(order)

    def _deliver_and_invoice(self, order, delivered, deduct=True):
        product_lines = order.order_line.filtered(
            lambda line: not line.is_downpayment
        )
        product_lines.qty_delivered = delivered
        return order._create_invoices(final=deduct)

    def _deduction(self, invoice, order=None):
        lines = invoice.invoice_line_ids.filtered(
            lambda line: (
                line.is_downpayment
                and line.quantity < 0
                and (not order or order in line.sale_line_ids.order_id)
            )
        )
        return -sum(lines.mapped("price_subtotal"))

    def test_three_invoices_consume_30_percent(self):
        order = self._make_order()
        advance = self._make_advance(order)
        self.assertAlmostEqual(advance.amount_untaxed, 3000.0, places=2)
        advance.action_post()
        invoiced = []
        for qty, expected_base, expected_dp, expected_balance in (
            (2, 2000, 600, 1400),
            (5, 3000, 900, 2100),
            (10, 5000, 1500, 3500),
        ):
            invoice = self._deliver_and_invoice(order, qty)
            self.assertEqual(len(invoice), 1)
            self.assertAlmostEqual(self._deduction(invoice), expected_dp, places=2)
            self.assertAlmostEqual(invoice.amount_untaxed, expected_balance, places=2)
            self.assertAlmostEqual(
                sum(
                    invoice.invoice_line_ids.filtered(
                        lambda line: not line.is_downpayment
                        and line.display_type == "product"
                    ).mapped("price_subtotal")
                ),
                expected_base,
                places=2,
            )
            invoice.action_post()
            invoiced.append(invoice)
        self.assertAlmostEqual(sum(self._deduction(inv) for inv in invoiced), 3000)
        self.assertFalse(
            order.order_line.filtered("is_downpayment").filtered(
                lambda line: not line.display_type
            ).filtered("qty_to_invoice")
        )

    def test_fixed_advance_and_two_partial_invoices(self):
        order = self._make_order()
        self._make_advance(order, fixed=2500)
        first = self._deliver_and_invoice(order, 4)
        self.assertAlmostEqual(self._deduction(first), 1000.0, places=2)
        first.action_post()
        second = self._deliver_and_invoice(order, 10)
        self.assertAlmostEqual(self._deduction(second), 1500.0, places=2)

    def test_two_separate_advance_invoices(self):
        order = self._make_order()
        self._make_advance(order, percent=10)
        self._make_advance(order, percent=20)
        partial = self._deliver_and_invoice(order, 2)
        self.assertAlmostEqual(self._deduction(partial), 600.0, places=2)
        self.assertEqual(
            len(partial.invoice_line_ids.filtered(lambda l: l.is_downpayment)), 2
        )

    def test_advance_remains_when_deduction_disabled(self):
        order = self._make_order()
        self._make_advance(order)
        partial = self._deliver_and_invoice(order, 2, deduct=False)
        self.assertAlmostEqual(self._deduction(partial), 0, places=2)
        self.assertAlmostEqual(partial.amount_untaxed, 2000, places=2)

    def test_cancel_draft_releases_reservation(self):
        order = self._make_order()
        self._make_advance(order)
        first = self._deliver_and_invoice(order, 2)
        self.assertAlmostEqual(self._deduction(first), 600, places=2)
        first.button_cancel()
        self.assertEqual(first.state, "cancel")
        replacement = self._deliver_and_invoice(order, 2)
        self.assertAlmostEqual(self._deduction(replacement), 600, places=2)

    def test_consolidated_invoice_keeps_order_specific_amounts(self):
        first_order = self._make_order()
        second_order = self._make_order()
        self._make_advance(first_order)
        self._make_advance(second_order, percent=50)
        for order in (first_order, second_order):
            order.order_line.filtered(
                lambda line: not line.is_downpayment
            ).qty_delivered = 2
        invoice = (first_order | second_order)._create_invoices(
            final=True, grouped=False
        )
        self.assertEqual(len(invoice), 1)
        self.assertAlmostEqual(self._deduction(invoice, first_order), 600, places=2)
        self.assertAlmostEqual(self._deduction(invoice, second_order), 1000, places=2)

    def test_tax_metadata_and_vat_are_prorated(self):
        vat = self.env["account.tax"].create(
            {
                "name": "21% VAT down payment test",
                "amount_type": "percent",
                "amount": 21.0,
                "type_tax_use": "sale",
                "company_id": self.env.company.id,
            }
        )
        order = self._make_order(taxes=vat)
        advance = self._make_advance(order)
        self.assertAlmostEqual(advance.amount_untaxed, 3000.0, places=2)
        partial = self._deliver_and_invoice(order, 2)
        self.assertAlmostEqual(self._deduction(partial), 600.0, places=2)
        self.assertAlmostEqual(partial.amount_untaxed, 1400, places=2)
        self.assertAlmostEqual(partial.amount_tax, 294, places=2)
        dp_line = partial.invoice_line_ids.filtered("is_downpayment").filtered(
            lambda line: line.display_type == "product"
        )
        self.assertEqual(len(dp_line), 1)
        self.assertEqual(dp_line.quantity, -1)
        if "price_unit" in (dp_line.extra_tax_data or {}):
            self.assertAlmostEqual(
                dp_line.extra_tax_data["price_unit"], dp_line.price_unit, places=2
            )
