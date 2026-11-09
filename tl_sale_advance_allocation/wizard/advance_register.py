from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvanceRegisterWizard(models.TransientModel):
    _name = "tl.sale.advance.register.wizard"
    _description = "Register an Existing Fiscal Advance Invoice"

    invoice_id = fields.Many2one("account.move", required=True)
    blanket_order_id = fields.Many2one("sale.blanket.order", required=True)
    invoice_line_id = fields.Many2one(
        "account.move.line", required=True, domain="[('move_id', '=', invoice_id)]"
    )

    def action_register(self):
        self.ensure_one()
        move = self.invoice_id
        if not self.env.user.has_group("account.group_account_user"):
            raise UserError(_("Accounting permission is required."))
        if move.move_type not in ("out_invoice", "in_invoice"):
            raise UserError(_("Select a customer/vendor advance invoice."))
        if self.env["tl.sale.advance"].search_count([
            ("invoice_line_id", "=", self.invoice_line_id.id)
        ]):
            raise UserError(_("The advance line is already registered."))
        advance = self.env["tl.sale.advance"].create({
            "blanket_order_id": self.blanket_order_id.id,
            "kind": "customer" if move.move_type == "out_invoice" else "supplier",
            "invoice_id": move.id,
            "invoice_line_id": self.invoice_line_id.id,
        })
        return advance.action_view_invoice()
