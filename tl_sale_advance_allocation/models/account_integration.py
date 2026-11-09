# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class AccountMove(models.Model):
    _inherit = "account.move"

    # Optional hint for registering invoices issued specifically as advances.
    # Normal delivery invoices may involve ANY NUMBER of blanket contracts.
    tl_blanket_order_id = fields.Many2one(
        "sale.blanket.order", string="Advance contract (optional)",
        check_company=True, copy=False, index=True,
        domain="[('company_id', '=', company_id)]",
    )
    tl_advance_ids = fields.One2many("tl.sale.advance", "invoice_id", readonly=True)
    tl_allocation_ids = fields.One2many("tl.sale.advance.allocation", "invoice_id", readonly=True)

    def action_tl_create_advance(self):
        self.ensure_one()
        if self.move_type not in ("out_invoice", "in_invoice"):
            raise UserError(_("Register advances from customer/vendor invoices."))
        return {
            "type": "ir.actions.act_window", "name": _("Register existing advance invoice"),
            "res_model": "tl.sale.advance.register.wizard", "target": "new", "view_mode": "form",
            "context": {"default_invoice_id": self.id, "default_blanket_order_id": self.tl_blanket_order_id.id},
        }

    def action_tl_apply_advance(self):
        self.ensure_one()
        if self.state != "draft" or self.move_type not in ("out_invoice", "in_invoice"):
            raise UserError(_("Choose a draft customer/vendor invoice."))
        return {
            "type": "ir.actions.act_window", "name": _("Apply invoiced advance"),
            "res_model": "tl.sale.advance.apply.wizard", "target": "new", "view_mode": "form",
            "context": {"default_invoice_id": self.id},
        }

    def _tl_positive_contract_lines(self, advance):
        self.ensure_one()
        contract = advance.blanket_order_id
        result = self.env["account.move.line"]
        for line in self.invoice_line_ids:
            if (line.price_subtotal <= 0 or line.tl_allocation_id
                    or set(line.tax_ids.ids) != set(advance.tax_ids.ids)):
                continue
            # For standard sale invoices, follow the native SO line mapping.
            sales_contracts = line.sale_line_ids.mapped("blanket_order_line.order_id")
            if contract in sales_contracts or line.tl_blanket_order_id == contract:
                result |= line
        return result

    def _tl_matching_amount(self, advance):
        self.ensure_one()
        positive = sum(self._tl_positive_contract_lines(advance).mapped("price_subtotal"))
        deducted = sum(
            allocation.amount_base for allocation in self.tl_allocation_ids
            if allocation.blanket_order_id == advance.blanket_order_id
            and set(allocation.advance_id.tax_ids.ids) == set(advance.tax_ids.ids)
        )
        return max(0, self.currency_id.round(positive - deducted))

    def _tl_apply_available(self):
        """Optional automatic proportional allocation, per contract and tax set.

        Off by default. Never uses a single contract value from the invoice header;
        mixed contract invoices are handled line by line.
        """
        for invoice in self:
            if (invoice.move_type != "out_invoice" or invoice.state != "draft"
                    or not invoice.company_id.tl_auto_allocate_sales):
                continue
            for sale_contract in invoice.invoice_line_ids.mapped(
                "sale_line_ids.blanket_order_line.order_id"
            ):
                advances = self.env["tl.sale.advance"].sudo().search([
                    ("blanket_order_id", "=", sale_contract.id),
                    ("kind", "=", "customer"),
                    ("invoice_id.state", "=", "posted"),
                    ("invoice_id.payment_state", "=", "paid"),
                ], order="id")
                for advance in advances:
                    if advance.amount_remaining <= 0 or sale_contract.amount_untaxed <= 0:
                        continue
                    eligible_base = sum(invoice._tl_positive_contract_lines(advance).mapped("price_subtotal"))
                    target = advance.currency_id.round(eligible_base * advance.amount_base / sale_contract.amount_untaxed)
                    already = sum(row.amount_base for row in advance.allocation_ids if row.invoice_id == invoice)
                    amount = min(advance.amount_remaining, max(0, target - already),
                                 invoice._tl_matching_amount(advance))
                    if amount > 0:
                        advance.with_context(tl_auto_advance_allocation=True)._tl_allocate_to(invoice.sudo(), amount)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Manual contract identification on supplier bills or non-SO-linked lines.
    tl_blanket_order_id = fields.Many2one(
        "sale.blanket.order", string="Blanket contract", check_company=True,
        copy=False, domain="[('company_id', '=', company_id)]",
    )
    tl_allocation_id = fields.Many2one(
        "tl.sale.advance.allocation", copy=False, readonly=True, ondelete="restrict",
    )


class SupplyAdvanceAllocateMixin(models.Model):
    _inherit = "tl.sale.advance"

    def _tl_allocate_to(self, invoice, amount):
        self.ensure_one()
        if (not self.env.context.get("tl_auto_advance_allocation")
                and not self.env.user.has_group("account.group_account_user")):
            raise UserError(_("Accounting permissions are required to allocate an advance."))
        if self.invoice_id.state != "posted" or self.invoice_id.payment_state != "paid":
            raise UserError(_("The advance invoice must be posted and paid."))
        if invoice.state != "draft" or invoice.move_type != self.invoice_id.move_type:
            raise UserError(_("The target must be a compatible draft invoice."))
        if (self.company_id != invoice.company_id or self.currency_id != invoice.currency_id):
            raise UserError(_("Company and currency must match."))
        if (self.kind == "customer"
                and self.partner_id.commercial_partner_id != invoice.partner_id.commercial_partner_id):
            raise UserError(_("The customer of the invoice does not match the advance."))
        # Multiple invoices/users cannot consume the same advance concurrently.
        self.env.cr.execute(
            "SELECT id FROM tl_sale_advance WHERE id = %s FOR UPDATE", [self.id]
        )
        self.invalidate_recordset(["amount_remaining"])
        amount = self.currency_id.round(amount)
        if amount <= 0 or amount > self.amount_remaining:
            raise UserError(_("Allocation exceeds remaining advance."))
        if amount > invoice._tl_matching_amount(self):
            raise UserError(_("The amount exceeds positive contract invoice lines with matching taxes."))
        line = self.env["account.move.line"].create({
            "move_id": invoice.id,
            "name": _("Application of advance %s") % self.invoice_id.name,
            "quantity": 1,
            "price_unit": -amount,
            "account_id": self.account_id.id,
            "tax_ids": [Command.set(self.tax_ids.ids)],
            "tl_blanket_order_id": self.blanket_order_id.id,
        })
        record = self.env["tl.sale.advance.allocation"].create({
            "advance_id": self.id, "invoice_id": invoice.id,
            "invoice_line_id": line.id, "amount_base": amount,
        })
        line.sudo().tl_allocation_id = record.id
        return record


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _create_invoices(self, *args, **kwargs):
        invoices = super()._create_invoices(*args, **kwargs)
        invoices._tl_apply_available()
        return invoices


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.tl_blanket_order_id:
            # Optional header default for standalone vendor advance bills.
            vals["tl_blanket_order_id"] = self.tl_blanket_order_id.id
        return vals
