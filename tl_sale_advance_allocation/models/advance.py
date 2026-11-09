# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    tl_customer_advance_account_id = fields.Many2one(
        "account.account", string="Customer advances (438)", check_company=True,
        domain="[('active', '=', True), ('account_type', '=', 'liability_current')]",
    )
    tl_supplier_advance_account_id = fields.Many2one(
        "account.account", string="Supplier advances (407)", check_company=True,
        domain="[('active', '=', True), ('account_type', '=', 'asset_current')]",
    )
    tl_auto_allocate_sales = fields.Boolean(
        string="Automatically allocate advances to customer invoices",
        help="Opt-in. Uses the proportion of contract base invoiced, per contract and tax set.",
        default=False,
    )


class SupplyAdvance(models.Model):
    _name = "tl.sale.advance"
    _description = "Fiscal Advance Invoice for Blanket Contract"
    _order = "id desc"
    _check_company_auto = True

    blanket_order_id = fields.Many2one(
        "sale.blanket.order", required=True, index=True,
        ondelete="restrict", check_company=True,
    )
    company_id = fields.Many2one(
        "res.company", related="blanket_order_id.company_id", store=True,
    )
    currency_id = fields.Many2one("res.currency", related="invoice_id.currency_id")
    kind = fields.Selection(
        [("customer", "Customer"), ("supplier", "Supplier")], required=True,
    )
    invoice_id = fields.Many2one(
        "account.move", required=True, copy=False, index=True,
        ondelete="restrict", check_company=True,
    )
    invoice_line_id = fields.Many2one(
        "account.move.line", required=True, ondelete="restrict", check_company=True,
    )
    partner_id = fields.Many2one("res.partner", related="invoice_id.partner_id", store=True)
    tax_ids = fields.Many2many("account.tax", related="invoice_line_id.tax_ids")
    account_id = fields.Many2one("account.account", related="invoice_line_id.account_id")
    amount_base = fields.Monetary(compute="_compute_amounts", currency_field="currency_id")
    amount_applied = fields.Monetary(compute="_compute_amounts", currency_field="currency_id")
    amount_remaining = fields.Monetary(compute="_compute_amounts", currency_field="currency_id")
    allocation_ids = fields.One2many("tl.sale.advance.allocation", "advance_id", readonly=True)
    invoice_state = fields.Selection(related="invoice_id.state")
    payment_state = fields.Selection(related="invoice_id.payment_state")

    @api.constrains("blanket_order_id", "invoice_id", "invoice_line_id", "kind")
    def _check_document(self):
        for advance in self:
            invoice = advance.invoice_id
            if invoice.move_type != ("out_invoice" if advance.kind == "customer" else "in_invoice"):
                raise ValidationError(_("Wrong fiscal advance invoice type."))
            if (invoice.company_id != advance.company_id
                    or invoice.currency_id != advance.blanket_order_id.currency_id
                    or advance.invoice_line_id.move_id != invoice):
                raise ValidationError(_("Advance company, currency or invoice line does not match the contract."))
            if (advance.kind == "customer"
                    and invoice.partner_id.commercial_partner_id
                    != advance.blanket_order_id.partner_id.commercial_partner_id):
                raise ValidationError(_("Advance customer is not the blanket contract customer."))
            expected_account = (advance.company_id.tl_customer_advance_account_id
                                if advance.kind == "customer" else advance.company_id.tl_supplier_advance_account_id)
            account_type = "liability_current" if advance.kind == "customer" else "asset_current"
            if (not expected_account or advance.invoice_line_id.account_id != expected_account
                    or expected_account.account_type != account_type):
                raise ValidationError(_("Advance must use the configured 438/407 account."))
            if advance.invoice_line_id.price_subtotal <= 0:
                raise ValidationError(_("The fiscal advance line must have a positive taxable base."))

    @api.depends("invoice_line_id.price_subtotal", "invoice_id.state",
                 "allocation_ids.amount_base", "allocation_ids.invoice_id.state")
    def _compute_amounts(self):
        for advance in self:
            advance.amount_base = (advance.invoice_line_id.price_subtotal
                                   if advance.invoice_id.state != "cancel" else 0.0)
            advance.amount_applied = sum(a.amount_base for a in advance.allocation_ids
                                         if a.invoice_id.state != "cancel")
            advance.amount_remaining = advance.currency_id.round(
                advance.amount_base - advance.amount_applied
            ) if advance.currency_id else 0.0

    def action_view_invoice(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move",
                "res_id": self.invoice_id.id, "view_mode": "form"}


class SupplyAdvanceAllocation(models.Model):
    _name = "tl.sale.advance.allocation"
    _description = "Allocation of Invoiced Advance to Invoice"
    _order = "id desc"
    _check_company_auto = True

    advance_id = fields.Many2one("tl.sale.advance", required=True, ondelete="restrict", check_company=True)
    blanket_order_id = fields.Many2one("sale.blanket.order", related="advance_id.blanket_order_id", store=True)
    company_id = fields.Many2one("res.company", related="advance_id.company_id", store=True)
    currency_id = fields.Many2one("res.currency", related="advance_id.currency_id")
    invoice_id = fields.Many2one("account.move", required=True, ondelete="restrict", check_company=True)
    invoice_line_id = fields.Many2one("account.move.line", required=True, ondelete="restrict", check_company=True)
    amount_base = fields.Monetary(required=True, currency_field="currency_id")

    @api.constrains("advance_id", "invoice_id", "invoice_line_id", "amount_base")
    def _check_allocation(self):
        for row in self:
            advance, invoice = row.advance_id, row.invoice_id
            if (row.amount_base <= 0 or invoice == advance.invoice_id
                    or invoice.company_id != advance.company_id
                    or invoice.currency_id != advance.currency_id
                    or invoice.move_type != advance.invoice_id.move_type
                    or row.invoice_line_id.move_id != invoice):
                raise ValidationError(_("Allocation must match the invoice type, company and currency."))

    def unlink(self):
        if any(rec.invoice_id.state == "posted" for rec in self):
            raise UserError(_("Posted invoice allocations require a credit note."))
        lines = self.mapped("invoice_line_id")
        lines.write({"tl_allocation_id": False})
        result = super().unlink()
        lines.filtered(lambda l: l.move_id.state == "draft").unlink()
        return result
