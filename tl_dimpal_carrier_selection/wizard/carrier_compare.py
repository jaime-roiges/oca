from odoo import _, fields, models
from odoo.exceptions import UserError


class CarrierCompareWizard(models.TransientModel):
    _name = 'tl.dimpal.carrier.compare.wizard'
    _description = 'Comparison of Freight Rates'

    order_id = fields.Many2one('sale.order', required=True)
    currency_id = fields.Many2one('res.currency', related='order_id.currency_id')
    quote_ids = fields.One2many('tl.dimpal.carrier.quote', 'wizard_id', readonly=True)

    def action_compare(self):
        self.ensure_one()
        order = self.order_id
        order.check_access('write')
        if order.state not in ('draft', 'sent'):
            raise UserError(_('Only quotations can be compared.'))
        if not order.partner_shipping_id or not order.order_line:
            raise UserError(_('Set the shipping address and order lines first.'))
        carriers = self.env['delivery.carrier'].search([
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', order.company_id.id),
        ])
        self.quote_ids.unlink()
        Quote = self.env['tl.dimpal.carrier.quote']
        for carrier, price, success, note in order._dimpal_rate_carriers(carriers):
            Quote.create({
                'wizard_id': self.id, 'carrier_id': carrier.id,
                'price': price, 'success': success, 'message': note,
            })
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new'}


class CarrierQuote(models.TransientModel):
    _name = 'tl.dimpal.carrier.quote'
    _description = 'Carrier Rate Proposal'
    _order = 'success desc, price asc, id'

    wizard_id = fields.Many2one('tl.dimpal.carrier.compare.wizard', required=True,
                                 ondelete='cascade')
    carrier_id = fields.Many2one('delivery.carrier', required=True)
    currency_id = fields.Many2one('res.currency', related='wizard_id.currency_id')
    price = fields.Monetary()
    success = fields.Boolean()
    message = fields.Char()

    def action_choose(self):
        self.ensure_one()
        order = self.wizard_id.order_id
        order.check_access('write')
        if order.state not in ('draft', 'sent') or not self.success:
            raise UserError(_('The quote cannot be selected.'))
        # Refresh rate at the moment of selection to avoid stale pricing.
        refreshed = order._dimpal_best_carrier(self.carrier_id)
        if not refreshed or refreshed[0] != self.carrier_id:
            raise UserError(_('The selected carrier is no longer available.'))
        order.set_delivery_line(self.carrier_id, refreshed[1])
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order',
                'res_id': order.id, 'view_mode': 'form'}
