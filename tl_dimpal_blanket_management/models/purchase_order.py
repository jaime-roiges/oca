# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    dimpal_blanket_order_id = fields.Many2one(
        'sale.order', string='Customer blanket order', index=True, copy=False,
        check_company=True, domain="[('order_type','=','blanket'),('company_id','=',company_id)]",
    )

    @api.constrains('dimpal_blanket_order_id', 'company_id')
    def _check_dimpal_blanket_order(self):
        for order in self:
            blanket = order.dimpal_blanket_order_id
            if blanket and (blanket.order_type != 'blanket' or blanket.company_id != order.company_id):
                raise ValidationError(_('Purchase must reference a blanket order in the same company.'))
