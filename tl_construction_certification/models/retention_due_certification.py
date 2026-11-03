from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ConstructionCertification(models.Model):
    _inherit = "construction.certification"

    retention_due_date = fields.Date(
        string="Guarantee Maturity Date",
        copy=False,
        tracking=True,
        help="Date the guarantee retention becomes due. It is copied to the retention journal item.",
    )

    @api.onchange("sale_order_id")
    def _onchange_retention_due_order(self):
        for cert in self:
            cert.retention_due_date = cert.sale_order_id.construction_retention_due_date

    @api.model_create_multi
    def create(self, vals_list):
        default_order_id = self.env.context.get("default_sale_order_id")
        order_ids = {vals.get("sale_order_id", default_order_id) for vals in vals_list}
        dates = {order.id: order.construction_retention_due_date for order in self.env["sale.order"].browse([i for i in order_ids if i]).exists()}
        for vals in vals_list:
            order_id = vals.get("sale_order_id", default_order_id)
            if "retention_due_date" not in vals and dates.get(order_id):
                vals["retention_due_date"] = dates[order_id]
        return super().create(vals_list)

    def _prepare_adjustment_line(self, name, amount, account, adjustment_type):
        self.ensure_one()
        vals = super()._prepare_adjustment_line(name, amount, account, adjustment_type)
        if adjustment_type == "retention":
            if not self.retention_due_date:
                raise UserError(_("Set the guarantee maturity date before creating an invoice with retention."))
            vals["date_maturity"] = self.retention_due_date
        return vals

    def action_create_invoice(self):
        result = super().action_create_invoice()
        for cert in self:
            lines = cert.invoice_id.line_ids.filtered(
                lambda line: line.construction_adjustment_type == "retention"
                and line.construction_certification_id == cert
            )
            if lines and cert.retention_due_date:
                lines.write({"date_maturity": cert.retention_due_date})
        return result

    def _open_retention_maturity_lines(self):
        self.ensure_one()
        if not self.invoice_id:
            return self.env["account.move.line"]
        # Include linked credit notes while leaving unrelated manual 4308
        # entries and already fully reconciled history untouched.
        return self.env["account.move.line"].search([
            ("construction_certification_id", "=", self.id),
            ("construction_adjustment_type", "=", "retention"),
            ("move_id.state", "in", ("draft", "posted")),
            ("reconciled", "=", False),
        ])

    def write(self, vals):
        if "retention_due_date" not in vals:
            return super().write(vals)
        new_date = fields.Date.to_date(vals["retention_due_date"]) or False
        changed = self.filtered(lambda cert: cert.retention_due_date != new_date)
        for cert in changed:
            lines = cert._open_retention_maturity_lines()
            if lines and not new_date:
                raise UserError(_("A retention with an open journal item must have a guarantee maturity date."))
            if lines.filtered(lambda line: line.move_id.state == "posted") and not self.env.user.has_group("account.group_account_manager"):
                raise UserError(_("Only accounting managers can change the maturity date of a posted retention."))
        result = super().write(vals)
        for cert in changed:
            lines = cert._open_retention_maturity_lines()
            if lines:
                lines.write({"date_maturity": cert.retention_due_date})
        return result
