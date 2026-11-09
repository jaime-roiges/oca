from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class AccountMove(models.Model):
    _inherit = 'account.move'

    dimpal_blanket_order_id = fields.Many2one('sale.order', copy=False, index=True,
        check_company=True, domain="[('order_type','=','blanket'), ('company_id','=',company_id)]")
    dimpal_advance_ids = fields.One2many('tl.dimpal.advance', 'invoice_id', readonly=True)
    dimpal_allocation_ids = fields.One2many('tl.dimpal.advance.allocation', 'invoice_id', readonly=True)

    def action_dimpal_create_advance(self):
        self.ensure_one()
        if not self.dimpal_blanket_order_id:
            raise UserError(_('Link the invoice to a Dimpal contract first.'))
        return {'type': 'ir.actions.act_window', 'name': _('Register existing advance invoice'),
                'res_model': 'tl.dimpal.advance.register.wizard', 'target': 'new',
                'view_mode': 'form', 'context': {'default_invoice_id': self.id}}

    def action_dimpal_apply_advance(self):
        self.ensure_one()
        if self.state != 'draft' or not self.dimpal_blanket_order_id or self.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(_('Choose a draft customer/vendor invoice linked to a Dimpal contract.'))
        return {'type': 'ir.actions.act_window', 'name': _('Apply invoiced advances'),
                'res_model': 'tl.dimpal.advance.apply.wizard', 'target': 'new',
                'view_mode': 'form', 'context': {'default_invoice_id': self.id}}

    def _dimpal_apply_available(self):
        """Safe optional automatic deduction of paid, registered customer advances.

        Only draft invoices with a contract are considered. The cap is based on the
        positive, tax-compatible delivery lines, not the total invoice including freight.
        """
        Advance = self.env['tl.dimpal.advance'].sudo()
        for invoice in self:
            if (invoice.move_type != 'out_invoice' or invoice.state != 'draft'
                    or not invoice.dimpal_blanket_order_id or not invoice.company_id.dimpal_auto_allocate_sales):
                continue
            # Automatic processing is explicitly enabled by the company. Avoid
            # ACL failures on accounting-only allocation records for sales users.
            invoice = invoice.sudo()
            advances = Advance.search([
                ('blanket_order_id', '=', invoice.dimpal_blanket_order_id.id),
                ('kind', '=', 'customer'), ('invoice_id.state', '=', 'posted'),
                ('invoice_id.payment_state', '=', 'paid'),
            ], order='id')
            for advance in advances:
                if advance.amount_remaining <= 0:
                    continue
                contract = invoice.dimpal_blanket_order_id
                cap = invoice._dimpal_matching_amount(advance, contract_only=True)
                if cap <= 0:
                    continue
                # Compute the proportional target from the ORIGINAL taxable base,
                # not from the residual after preceding advance allocations.
                original_base = sum(
                    l.price_subtotal for l in invoice.invoice_line_ids
                    if l.price_subtotal > 0 and not l.dimpal_allocation_id
                    and l.sale_line_ids.filtered(lambda sl: sl.order_id._dimpal_get_blanket_order() == contract)
                    and set(l.tax_ids.ids) == set(advance.tax_ids.ids)
                )
                ratio = (advance.amount_base / contract.amount_untaxed
                         if contract.amount_untaxed > 0 else 0)
                already = sum(a.amount_base for a in advance.allocation_ids
                              if a.invoice_id == invoice)
                desired = max(0.0, advance.currency_id.round(original_base * ratio) - already)
                amount = min(advance.amount_remaining, desired, cap)
                if amount > 0:
                    advance.with_context(dimpal_automatic_allocation=True)._dimpal_allocate_to(invoice.sudo(), amount)

    def _dimpal_matching_amount(self, advance, contract_only=False):
        self.ensure_one()
        return self.currency_id.round(sum(
            line.price_subtotal
            for line in self.invoice_line_ids
            if line.price_subtotal > 0 and set(line.tax_ids.ids) == set(advance.tax_ids.ids)
            and not line.dimpal_allocation_id
            and (not contract_only or line.sale_line_ids.filtered(lambda sl: sl.order_id._dimpal_get_blanket_order() == self.dimpal_blanket_order_id))
        ) - sum(
            line.dimpal_allocation_id.amount_base
            for line in self.invoice_line_ids
            if line.dimpal_allocation_id and set(line.tax_ids.ids) == set(advance.tax_ids.ids)
        ))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    dimpal_allocation_id = fields.Many2one('tl.dimpal.advance.allocation',
                                           copy=False, readonly=True, ondelete='restrict')


class DimpalAdvanceAllocateMixin(models.Model):
    _inherit = 'tl.dimpal.advance'

    def _dimpal_allocate_to(self, invoice, amount):
        self.ensure_one()
        if (not self.env.context.get('dimpal_automatic_allocation')
                and not self.env.user.has_group('account.group_account_user')):
            raise UserError(_('Accounting permissions are required to allocate an advance.'))
        if (self.account_id not in (self.company_id.dimpal_customer_advance_account_id,
                                    self.company_id.dimpal_supplier_advance_account_id)
                or self.invoice_line_id.price_subtotal <= 0):
            raise UserError(_('Advance invoice must use the configured account and a positive base.'))
        if self.invoice_id.state != 'posted' or self.invoice_id.payment_state != 'paid':
            raise UserError(_('An advance invoice must be posted and paid before allocation.'))
        if invoice.state != 'draft' or invoice.move_type != self.invoice_id.move_type:
            raise UserError(_('Target must be a compatible draft invoice.'))
        if invoice.dimpal_blanket_order_id != self.blanket_order_id or invoice.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id:
            raise UserError(_('Advance and invoice have different contracts or partners.'))
        if self.currency_id != invoice.currency_id:
            raise UserError(_('Advance and invoice must be in the same currency.'))
        # Prevent two concurrent workers from allocating the same advance amount.
        self.env.cr.execute('SELECT id FROM tl_dimpal_advance WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['amount_remaining'])
        amount = self.currency_id.round(amount)
        if amount <= 0 or amount > self.amount_remaining:
            raise UserError(_('Amount exceeds the remaining invoiced advance.'))
        if amount > invoice._dimpal_matching_amount(self):
            raise UserError(_('Amount exceeds remaining positive lines with matching taxes.'))
        line = self.env['account.move.line'].create({
            'move_id': invoice.id,
            'name': _('Application of advance %s') % self.invoice_id.name,
            'quantity': 1, 'price_unit': -amount,
            'account_id': self.account_id.id,
            'tax_ids': [Command.set(self.tax_ids.ids)],
        })
        allocation = self.env['tl.dimpal.advance.allocation'].create({
            'advance_id': self.id, 'invoice_id': invoice.id,
            'invoice_line_id': line.id, 'amount_base': amount,
        })
        line.sudo().dimpal_allocation_id = allocation.id
        return allocation


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        blanket = self._dimpal_get_blanket_order()
        if blanket:
            vals['dimpal_blanket_order_id'] = blanket.id
        return vals

    def _get_invoice_grouping_keys(self):
        return [*super()._get_invoice_grouping_keys(), 'dimpal_blanket_order_id']

    def _create_invoices(self, final=False, grouped=False):
        invoices = super()._create_invoices(final=final, grouped=grouped)
        invoices._dimpal_apply_available()
        return invoices


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.dimpal_blanket_order_id:
            vals['dimpal_blanket_order_id'] = self.dimpal_blanket_order_id.id
        return vals

    def action_create_invoice(self, attachment_ids=False):
        contracts = self.filtered('dimpal_blanket_order_id').mapped('dimpal_blanket_order_id')
        if len(contracts) > 1 or (contracts and any(not po.dimpal_blanket_order_id for po in self)):
            raise UserError(_('Bill Dimpal purchase contracts separately to preserve advance allocations.'))
        return super().action_create_invoice(attachment_ids=attachment_ids)
