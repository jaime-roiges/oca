from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    dimpal_customer_advance_account_id = fields.Many2one(
        'account.account', string='Customer advances (438)', check_company=True,
        domain="[('deprecated', '=', False)]",
    )
    dimpal_supplier_advance_account_id = fields.Many2one(
        'account.account', string='Supplier advances (407)', check_company=True,
        domain="[('deprecated', '=', False)]",
    )
    dimpal_auto_allocate_sales = fields.Boolean(
        string='Proportionally allocate advance to customer delivery invoices', default=False,
    )


class DimpalAdvance(models.Model):
    _name = 'tl.dimpal.advance'
    _description = 'Fiscal Advance Invoice Linked to Contract'
    _order = 'id desc'
    _check_company_auto = True

    blanket_order_id = fields.Many2one('sale.order', required=True, index=True,
                                   ondelete='restrict', check_company=True)
    company_id = fields.Many2one('res.company', related='blanket_order_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='invoice_id.currency_id')
    kind = fields.Selection([('customer', 'Customer'), ('supplier', 'Supplier')], required=True)
    invoice_id = fields.Many2one('account.move', required=True, ondelete='restrict',
                                  index=True, copy=False, check_company=True)
    invoice_line_id = fields.Many2one('account.move.line', required=True, ondelete='restrict',
                                       check_company=True)
    partner_id = fields.Many2one('res.partner', related='invoice_id.partner_id', store=True)
    tax_ids = fields.Many2many('account.tax', related='invoice_line_id.tax_ids')
    account_id = fields.Many2one('account.account', related='invoice_line_id.account_id')
    amount_base = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    amount_applied = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    amount_remaining = fields.Monetary(compute='_compute_amounts', currency_field='currency_id')
    allocation_ids = fields.One2many('tl.dimpal.advance.allocation', 'advance_id', readonly=True)
    invoice_state = fields.Selection(related='invoice_id.state')
    payment_state = fields.Selection(related='invoice_id.payment_state')

    @api.constrains('invoice_id', 'invoice_line_id', 'kind', 'blanket_order_id')
    def _check_document(self):
        for advance in self:
            move = advance.invoice_id
            if advance.blanket_order_id.order_type != 'blanket':
                raise ValidationError(_('Advance must reference an OCA blanket order.'))
            expected = 'out_invoice' if advance.kind == 'customer' else 'in_invoice'
            if (move.move_type != expected or move.company_id != advance.company_id
                    or advance.invoice_line_id.move_id != move
                    or move.currency_id != advance.blanket_order_id.currency_id):
                raise ValidationError(_('Advance invoice type, company, line or currency mismatch.'))
            if advance.kind == 'customer' and (
                move.partner_id.commercial_partner_id != advance.blanket_order_id.partner_id.commercial_partner_id
            ):
                raise ValidationError(_('The customer is not the contract customer.'))
            account = (advance.company_id.dimpal_customer_advance_account_id
                       if advance.kind == 'customer'
                       else advance.company_id.dimpal_supplier_advance_account_id)
            if not account or account != advance.invoice_line_id.account_id:
                raise ValidationError(_('The advance line must use the configured 438/407 account.'))
            kind = 'liability_current' if advance.kind == 'customer' else 'asset_current'
            if account.account_type != kind:
                raise ValidationError(_('The fiscal advance account has the wrong accounting type.'))
            if advance.invoice_line_id.price_subtotal <= 0:
                raise ValidationError(_('Advance invoice base must be positive.'))

    @api.depends('invoice_line_id.price_subtotal', 'invoice_id.state',
                 'allocation_ids.amount_base', 'allocation_ids.invoice_id.state')
    def _compute_amounts(self):
        for advance in self:
            advance.amount_base = (advance.invoice_line_id.price_subtotal
                                   if advance.invoice_id.state != 'cancel' else 0.0)
            advance.amount_applied = sum(a.amount_base for a in advance.allocation_ids
                                         if a.invoice_id.state != 'cancel')
            advance.amount_remaining = advance.currency_id.round(
                advance.amount_base - advance.amount_applied
            )

    def action_view_invoice(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move',
                'res_id': self.invoice_id.id, 'view_mode': 'form'}


class DimpalAdvanceAllocation(models.Model):
    _name = 'tl.dimpal.advance.allocation'
    _description = 'Allocation of Invoiced Advance to Contract Delivery Invoice'
    _order = 'id desc'
    _check_company_auto = True

    advance_id = fields.Many2one('tl.dimpal.advance', required=True, ondelete='restrict',
                                  check_company=True)
    blanket_order_id = fields.Many2one('sale.order', related='advance_id.blanket_order_id', store=True)
    company_id = fields.Many2one('res.company', related='advance_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='advance_id.currency_id')
    invoice_id = fields.Many2one('account.move', required=True, ondelete='restrict',
                                  check_company=True)
    invoice_line_id = fields.Many2one('account.move.line', required=True, ondelete='restrict',
                                       check_company=True)
    amount_base = fields.Monetary(required=True)

    @api.constrains('advance_id', 'invoice_id', 'invoice_line_id', 'amount_base')
    def _check_allocation(self):
        for allocation in self:
            advance, invoice = allocation.advance_id, allocation.invoice_id
            if (allocation.amount_base <= 0 or invoice == advance.invoice_id
                    or invoice.company_id != advance.company_id
                    or invoice.dimpal_blanket_order_id != advance.blanket_order_id
                    or invoice.currency_id != advance.currency_id
                    or invoice.move_type != advance.invoice_id.move_type
                    or allocation.invoice_line_id.move_id != invoice):
                raise ValidationError(_('Invalid advance allocation: incompatible invoice or amount.'))

    def unlink(self):
        if any(line.invoice_id.state == 'posted' for line in self):
            raise UserError(_('You cannot remove allocations from posted invoices. Use a credit note.'))
        invoice_lines = self.mapped('invoice_line_id')
        invoice_lines.write({'dimpal_allocation_id': False})
        result = super().unlink()
        invoice_lines.filtered(lambda line: line.move_id.state == 'draft').unlink()
        return result
