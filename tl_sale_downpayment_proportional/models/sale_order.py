# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Proportional consumption of Odoo 20's native down-payment invoices.

Only generated, negative down-payment lines are adjusted.  The original
advance invoices and the corresponding sale.order.line records stay intact.
"""

from odoo import models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

from .downpayment_utils import allocation_amount, scaled_extra_tax_data


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _create_invoices(self, final=False, grouped=False):
        # Serialize concurrent invoice creation for the same SO. Otherwise two
        # transactions could consume the same advance before either commits.
        if final and self:
            self.env.cr.execute(
                "SELECT id FROM sale_order WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                (self.ids,),
            )
        return super()._create_invoices(final=final, grouped=grouped)

    def _create_account_invoices(self, invoice_vals_list):
        # Core's hook runs *after* grouping, but before refund conversion and
        # analytic links. At this point the real invoice taxes are available.
        invoices = super()._create_account_invoices(invoice_vals_list)
        for invoice in invoices.filtered(lambda move: move.move_type == "out_invoice"):
            self._tl_prorate_invoice_downpayments(invoice)
        return invoices

    def _tl_prorate_invoice_downpayments(self, invoice):
        """Limit the native negative advance lines on a newly created invoice.

        Work per originating SO so that consolidated invoices behave like
        individual invoices. Money is calculated in the invoice/SO currency.
        """
        downpayment_lines = invoice.invoice_line_ids.filtered(
            lambda line: (
                line.is_downpayment
                and line.quantity < 0
                and line.sale_line_ids
                and line.display_type == "product"
            )
        )
        if not downpayment_lines:
            return

        lines_by_order = {}
        for line in invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product" and line.sale_line_ids
        ):
            orders = line.sale_line_ids.order_id
            if len(orders) != 1:
                raise UserError(
                    self.env._(
                        "Cannot prorate an invoice line linked to several sales "
                        "orders. Create separate invoice lines for each order."
                    )
                )
            order = orders
            lines_by_order.setdefault(order, self.env["account.move.line"])
            lines_by_order[order] |= line

        for order, current_lines in lines_by_order.items():
            current_downpayments = current_lines & downpayment_lines
            if not current_downpayments:
                continue
            currency = order.currency_id
            if invoice.currency_id != currency:
                raise UserError(
                    self.env._(
                        "The invoice and sales order currencies differ. The "
                        "advance cannot be deducted proportionally."
                    )
                )

            sale_product_lines = order.order_line.filtered(
                lambda line: not line.is_downpayment and not line.display_type
            )
            order_base = currency.round(
                sum(sale_product_lines.mapped("price_subtotal"))
            )
            if currency.compare_amounts(order_base, 0) <= 0:
                raise UserError(
                    self.env._(
                        "The sales order has no positive untaxed base on which "
                        "to calculate the proportional advance deduction."
                    )
                )

            current_base = currency.round(
                sum((current_lines - current_downpayments).mapped("price_subtotal"))
            )
            if currency.compare_amounts(current_base, 0) <= 0:
                raise UserError(
                    self.env._(
                        "The new invoice has no positive product amount against "
                        "which to deduct the down payment."
                    )
                )

            current_total = currency.round(
                sum((current_lines - current_downpayments).mapped("price_total"))
            )
            if currency.compare_amounts(current_total, 0) <= 0:
                raise UserError(
                    self.env._(
                        "The new invoice has no positive tax-included product amount "
                        "against which to deduct the down payment."
                    )
                )

            # Include posted and draft product invoices except cancelled ones.
            # Refunds are subtracted, and the invoice currently being created
            # is excluded to avoid counting it twice.
            historical_product_base = 0.0
            for old_line in sale_product_lines.invoice_lines:
                if old_line.move_id == invoice or old_line.move_id.state == "cancel":
                    continue
                if old_line.move_id.move_type in ("out_invoice", "out_refund"):
                    sign = 1 if old_line.move_id.move_type == "out_invoice" else -1
                    historical_product_base += sign * old_line.price_subtotal

            is_last = currency.compare_amounts(
                historical_product_base + current_base, order_base
            ) >= 0
            # Never deduct more than the value of products on this SO/invoice.
            remaining_invoice_base = current_base
            remaining_invoice_total = current_total
            for dp_line in current_downpayments.sorted("id"):
                origin = dp_line.sale_line_ids
                if len(origin) != 1 or not origin.is_downpayment:
                    raise UserError(
                        self.env._(
                            "The down payment invoice line must be linked to one "
                            "standard sales-order advance line."
                        )
                    )
                advance_credit = 0.0
                for old_line in origin.invoice_lines:
                    if (
                        old_line.move_id == invoice
                        or old_line.move_id.state == "cancel"
                    ):
                        continue
                    if old_line.move_id.move_type not in ("out_invoice", "out_refund"):
                        continue
                    sign = 1 if old_line.move_id.move_type == "out_invoice" else -1
                    advance_credit += sign * old_line.price_subtotal

                available = max(0.0, currency.round(advance_credit))
                full_deduction = -dp_line.price_subtotal
                full_deduction_total = -dp_line.price_total
                if currency.compare_amounts(full_deduction, 0) <= 0:
                    raise UserError(
                        self.env._("Invalid down payment deduction on the invoice.")
                    )
                # Odoo's standard draft line is for *all* the advance. Use
                # its actual tax-excluded base as the scaling reference.
                if currency.compare_amounts(full_deduction_total, 0) <= 0:
                    raise UserError(
                        self.env._("Invalid tax-included down payment deduction.")
                    )
                # Also limit the deduction by the gross amount, preventing a
                # negative invoice when the advance and products use different taxes.
                gross_room_as_base = max(
                    0.0,
                    remaining_invoice_total * full_deduction / full_deduction_total,
                )
                target = allocation_amount(
                    currency=currency,
                    full_base=full_deduction,
                    available=available,
                    current_product_base=current_base,
                    order_product_base=order_base,
                    invoice_room=min(remaining_invoice_base, gross_room_as_base),
                    is_last=is_last,
                )
                remaining_invoice_base = currency.round(
                    remaining_invoice_base - target
                )
                self._tl_set_downpayment_amount(dp_line, target, full_deduction)
                remaining_invoice_total = currency.round(
                    remaining_invoice_total + dp_line.price_total
                )

    def _tl_set_downpayment_amount(self, line, desired_base, full_base):
        """Scale price and Odoo 20 manual tax metadata, but NOT quantity.

        Keeping quantity=-1 avoids losing cents through Product Unit rounding.
        The 'extra_tax_data' mirror values must match the scaled unit price so
        that Odoo's tax engine keeps the correct original tax repartition.
        """
        factor = desired_base / full_base
        extra = scaled_extra_tax_data(line.extra_tax_data, factor)
        line.write({"price_unit": line.price_unit * factor, "extra_tax_data": extra})
        # If there is no non-zero target, Odoo's price has effectively become
        # zero; keep the SO link so the source advance remains traceable.
        currency = line.currency_id
        if not float_is_zero(desired_base, precision_rounding=currency.rounding):
            if abs(line.price_subtotal + desired_base) > currency.rounding + 1e-8:
                raise UserError(
                    self.env._(
                        "The prorated down payment differs from its expected "
                        "untaxed amount. Check the invoice's tax configuration."
                    )
                )
