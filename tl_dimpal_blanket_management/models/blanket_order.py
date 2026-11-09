# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dimpal_portal_visible = fields.Boolean(
        string='Show blanket order in Dimpal portal', default=True, copy=False,
        help='Only relevant for OCA blanket orders; customer access rules still apply.',
    )
    dimpal_purchase_ids = fields.One2many(
        'purchase.order', 'dimpal_blanket_order_id', string='Purchases for blanket order',
    )
    dimpal_purchase_count = fields.Integer(compute='_compute_dimpal_purchase_count')

    @api.depends('dimpal_purchase_ids')
    def _compute_dimpal_purchase_count(self):
        for order in self:
            order.dimpal_purchase_count = len(order.dimpal_purchase_ids)

    def action_dimpal_view_purchases(self):
        self.ensure_one()
        if self.order_type != 'blanket':
            raise UserError(_('Select a blanket sales order.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Supplier orders for blanket'),
            'res_model': 'purchase.order', 'view_mode': 'list,form',
            'domain': [('dimpal_blanket_order_id', '=', self.id)],
            'context': {'default_dimpal_blanket_order_id': self.id},
        }

    def _dimpal_get_blanket_order(self):
        self.ensure_one()
        return self if self.order_type == 'blanket' else (
            self.blanket_order_id if self.order_type == 'call_off' else self.env['sale.order']
        )
