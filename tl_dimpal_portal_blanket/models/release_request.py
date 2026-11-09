# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class DimpalReleaseRequest(models.Model):
    _name = 'tl.dimpal.release.request'
    _description = 'Customer request for OCA blanket call-off'
    _order = 'id desc'
    _check_company_auto = True

    blanket_order_id = fields.Many2one('sale.order', required=True, index=True,
        ondelete='restrict', check_company=True,
        domain="[('order_type','=','blanket')]")
    company_id = fields.Many2one('res.company', related='blanket_order_id.company_id', store=True)
    line_id = fields.Many2one('sale.order.line', required=True,
        ondelete='restrict', check_company=True)
    partner_id = fields.Many2one('res.partner', required=True, index=True)
    quantity = fields.Float(required=True, digits='Product Unit')
    notes = fields.Text()
    state = fields.Selection([('pending','Pending'), ('approved','Approved'),
                              ('rejected','Rejected')], default='pending', required=True)
    sale_order_id = fields.Many2one('sale.order', readonly=True, copy=False, check_company=True)

    @api.constrains('blanket_order_id', 'line_id', 'partner_id', 'quantity')
    def _check_request(self):
        for rec in self:
            if rec.blanket_order_id.order_type != 'blanket' or rec.line_id.order_id != rec.blanket_order_id:
                raise ValidationError(_('Request line must belong to a blanket order.'))
            if rec.partner_id.commercial_partner_id != rec.blanket_order_id.partner_id.commercial_partner_id:
                raise ValidationError(_('Requesting partner does not match blanket customer.'))
            if not rec.line_id.product_uom_id or float_compare(
                rec.quantity, 0, precision_rounding=rec.line_id.product_uom_id.rounding
            ) <= 0:
                raise ValidationError(_('Requested quantity must be positive.'))

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_salesman'):
            raise UserError(_('Sales permissions are required.'))
        if self.state != 'pending' or self.blanket_order_id.state != 'sale':
            raise UserError(_('Only pending requests on confirmed blanket orders can be approved.'))
        # Serialize concurrent approvals for the same blanket order.
        self.env.cr.execute('SELECT id FROM sale_order WHERE id = %s FOR UPDATE', [self.blanket_order_id.id])
        self.line_id.invalidate_recordset(['call_off_remaining_qty'])
        if float_compare(self.quantity, self.line_id.call_off_remaining_qty,
                         precision_rounding=self.line_id.product_uom_id.rounding) > 0:
            raise UserError(_('The remaining contractual quantity is insufficient.'))
        # The OCA native wizard creates the call-off with the OCA's own validations,
        # reservation tracking, and unit-of-measure conversions. No duplicate logic.
        wizard = self.env['sale.order.deliver.remaining.wizard'].create({
            'order_id': self.blanket_order_id.id,
            'wizard_line_ids': [Command.create({
                'sale_order_line_id': self.line_id.id,
                'qty_to_deliver': self.quantity,
            })],
        })
        action = wizard.action_create_call_off()
        call_off = self.env['sale.order'].browse(action['res_id'])
        call_off.action_confirm()
        self.write({'state': 'approved', 'sale_order_id': call_off.id})
        return action

    def action_reject(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only pending requests can be rejected.'))
        self.write({'state': 'rejected'})
        return True
