# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Highest number ever issued, including certifications later deleted.
    # Stored under the existing sale-order row lock during assignment.
    construction_last_certification_number = fields.Integer(
        string="Last Issued Construction Certification Number",
        readonly=True,
        copy=False,
        default=0,
    )

    certification_ids = fields.One2many(
        comodel_name="construction.certification",
        inverse_name="sale_order_id",
        string="Work Certifications",
    )
    certification_count = fields.Integer(
        compute="_compute_certification_count",
    )
    advance_ids = fields.One2many(
        comodel_name="construction.advance",
        inverse_name="sale_order_id",
        string="Advances",
    )
    advance_count = fields.Integer(
        compute="_compute_advance_count",
    )
    amount_advance_pending = fields.Monetary(
        string="Pending Advances",
        compute="_compute_advance_amounts",
        currency_field="currency_id",
    )

    def _compute_certification_count(self):
        for order in self:
            order.certification_count = len(order.certification_ids)

    def _compute_advance_count(self):
        for order in self:
            order.advance_count = len(order.advance_ids)

    def _compute_advance_amounts(self):
        for order in self:
            order.amount_advance_pending = sum(
                order.advance_ids.filtered(lambda a: a.state in ("confirmed", "applied")).mapped("amount_pending")
            )

    def action_view_certifications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Work Certifications",
            "res_model": "construction.certification",
            "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {"default_sale_order_id": self.id},
        }

    def action_view_advances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Advances",
            "res_model": "construction.advance",
            "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "context": {"default_sale_order_id": self.id},
        }

    def write(self, vals):
        res = super().write(vals)
        if "document_tax_mode" in vals:
            self.order_line._sync_open_certification_prices()
        return res

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    certification_line_ids = fields.One2many(
        comodel_name="construction.certification.line",
        inverse_name="sale_line_id",
        string="Certification Lines",
    )

    @api.depends(
        "invoice_lines.move_id.state",
        "invoice_lines.quantity",
        "certification_line_ids.qty_period",
        "certification_line_ids.certification_id.state",
        "certification_line_ids.certification_id.invoice_id.state",
        "certification_line_ids.invoice_line_ids.quantity",
        "certification_line_ids.invoice_line_ids.move_id.state",
        "certification_line_ids.invoice_line_ids.move_id.reversed_entry_id",
    )
    def _compute_qty_invoiced(self):
        super()._compute_qty_invoiced()
        grouped = self.env["construction.certification.line"]._read_group(
            domain=[
                ("sale_line_id", "in", self.ids),
                ("certification_id.state", "=", "invoiced"),
                ("certification_id.invoice_id.state", "in", ("draft", "posted")),
            ],
            groupby=["sale_line_id"],
            aggregates=["qty_period:sum"],
        )
        for sale_line, qty in grouped:
            sale_line.qty_invoiced += qty or 0.0
        credited_lines = self.env["account.move.line"].search([
            ("construction_certification_line_id.sale_line_id", "in", self.ids),
            ("construction_certification_line_id.certification_id.state", "=", "invoiced"),
            ("construction_certification_line_id.certification_id.invoice_id.state", "in", ("draft", "posted")),
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_refund", "in_refund")),
            ("move_id.reversed_entry_id.move_type", "in", ("out_invoice", "in_invoice")),
            ("construction_adjustment_type", "=", False),
        ])
        credited_lines = self.env["construction.certification.line"]._without_reversed_credits(
            credited_lines
        )
        by_sale = {}
        for line in credited_lines:
            sale_line = line.construction_certification_line_id.sale_line_id
            if sale_line:
                by_sale[sale_line.id] = by_sale.get(sale_line.id, 0.0) + abs(line.quantity or 0.0)
        for line in self:
            credited_qty = by_sale.get(line.id, 0.0)
            if credited_qty:
                line.qty_invoiced = max(line.qty_invoiced - credited_qty, 0.0)

    @api.depends(
        "qty_invoiced",
        "qty_delivered",
        "product_uom_qty",
        "state",
        "order_id.invoice_overages",
        "certification_line_ids.qty_period",
        "certification_line_ids.certification_id.state",
    )
    def _compute_qty_to_invoice(self):
        super()._compute_qty_to_invoice()
        grouped = self.env["construction.certification.line"]._read_group(
            domain=[
                ("sale_line_id", "in", self.ids),
                ("certification_id.state", "in", ("draft", "measured", "approved")),
            ],
            groupby=["sale_line_id"],
            aggregates=["qty_period:sum"],
        )
        reserved = {sale_line.id: qty or 0.0 for sale_line, qty in grouped}
        for line in self:
            held = reserved.get(line.id)
            if held:
                line.qty_to_invoice = max(line.qty_to_invoice - held, 0.0)

    def _sync_open_certification_prices(self):
        cert_lines = self.env["construction.certification.line"].search([
            ("sale_line_id", "in", self.ids),
            ("certification_id.state", "in", ("draft", "measured")),
        ])
        for line in cert_lines:
            line.price_unit = line._certified_price_unit(line.sale_line_id)

    def write(self, vals):
        res = super().write(vals)
        if {"price_unit", "discount", "tax_ids"} & set(vals):
            self._sync_open_certification_prices()
        return res
