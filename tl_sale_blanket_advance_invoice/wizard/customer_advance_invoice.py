# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import UserError


class CustomerAdvanceInvoiceWizard(models.TransientModel):
    _name = "tl.sale.blanket.advance.invoice.wizard"
    _description = "Issue a Customer Advance Invoice for a Blanket Contract"

    blanket_order_id = fields.Many2one(
        "sale.blanket.order", required=True, readonly=True,
    )
    company_id = fields.Many2one("res.company", related="blanket_order_id.company_id")
    currency_id = fields.Many2one("res.currency", related="blanket_order_id.currency_id")
    amount_base = fields.Monetary(
        string="Taxable advance base", currency_field="currency_id", required=True,
    )
    tax_ids = fields.Many2many(
        "account.tax", string="Sales VAT", required=True,
        domain="[('type_tax_use', '=', 'sale')]",
    )
    invoice_date = fields.Date(default=fields.Date.context_today, required=True)
    description = fields.Char(default="Contractual advance", required=True)

    def action_create_advance_invoice(self):
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_user"):
            raise UserError(_("Accounting permissions are required."))
        contract = self.blanket_order_id
        account = contract.company_id.tl_customer_advance_account_id
        if contract.state not in ("open", "done"):
            raise UserError(_("Confirm the blanket contract first."))
        if not account or not account.active or account.account_type != "liability_current":
            raise UserError(_("Configure a current-liability advance account (438)."))
        if self.amount_base <= 0:
            raise UserError(_("The taxable advance base must be positive."))
        if not self.tax_ids or any(
            tax.type_tax_use != "sale" or tax.company_id != contract.company_id
            for tax in self.tax_ids
        ):
            raise UserError(_("Select sales taxes of the contract company."))
        move = self.env["account.move"].with_company(contract.company_id).create({
            "move_type": "out_invoice",
            "company_id": contract.company_id.id,
            "partner_id": contract.partner_id.id,
            "currency_id": contract.currency_id.id,
            "invoice_date": self.invoice_date,
            "invoice_origin": contract.name,
            "tl_blanket_order_id": contract.id,
            "invoice_line_ids": [fields.Command.create({
                "name": self.description,
                "quantity": 1.0,
                "price_unit": self.amount_base,
                "account_id": account.id,
                "tax_ids": [fields.Command.set(self.tax_ids.ids)],
                "tl_blanket_order_id": contract.id,
            })],
        })
        advance_line = move.invoice_line_ids.filtered(lambda l: l.account_id == account)[:1]
        if not advance_line:
            raise UserError(_("Could not create the fiscal advance invoice line."))
        self.env["tl.sale.advance"].create({
            "blanket_order_id": contract.id,
            "kind": "customer",
            "invoice_id": move.id,
            "invoice_line_id": advance_line.id,
        })
        # The accountant must post the tax invoice, receive and reconcile the
        # payment. Allocation only accepts posted AND paid invoices.
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move", "res_id": move.id,
            "view_mode": "form", "name": _("Customer advance invoice"),
        }
