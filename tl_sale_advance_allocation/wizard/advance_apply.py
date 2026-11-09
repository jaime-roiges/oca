from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvanceApplyWizard(models.TransientModel):
    _name = "tl.sale.advance.apply.wizard"
    _description = "Apply Fiscal Advance to Partial Invoice"

    invoice_id = fields.Many2one("account.move", required=True)
    advance_id = fields.Many2one("tl.sale.advance", required=True)
    invoice_line_id = fields.Many2one(
        "account.move.line", string="Applicable invoice line",
        domain="[('move_id', '=', invoice_id)]",
        help="Optional for sales linked to OCA contract lines; for supplier bills, "
             "select the relevant positive line to link it to the blanket contract.",
    )
    amount_base = fields.Monetary(required=True)
    currency_id = fields.Many2one("res.currency", related="invoice_id.currency_id")

    def action_apply(self):
        self.ensure_one()
        self.invoice_id.check_access("write")
        if not self.env.user.has_group("account.group_account_user"):
            raise UserError(_("Accounting access is required."))
        if self.invoice_line_id:
            line = self.invoice_line_id
            if (line.move_id != self.invoice_id or line.price_subtotal <= 0
                    or line.tl_allocation_id or set(line.tax_ids.ids) != set(self.advance_id.tax_ids.ids)):
                raise UserError(_("Select a positive invoice line with the same taxes."))
            contract = self.advance_id.blanket_order_id
            related_contracts = line.sale_line_ids.mapped("blanket_order_line.order_id")
            if related_contracts and contract not in related_contracts:
                raise UserError(_("Invoice line belongs to a different blanket contract."))
            if line.tl_blanket_order_id and line.tl_blanket_order_id != contract:
                raise UserError(_("Invoice line is already allocated to another contract."))
            line.tl_blanket_order_id = contract
        self.advance_id._tl_allocate_to(self.invoice_id, self.amount_base)
        return {"type": "ir.actions.act_window", "name": _("Invoice with applied advance"),
                "res_model": "account.move", "res_id": self.invoice_id.id, "view_mode": "form"}
