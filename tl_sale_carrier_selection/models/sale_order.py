import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    tl_auto_web_cheapest = fields.Boolean(
        string='Prefer cheapest eligible carrier at website checkout', default=False,
    )
    tl_auto_sale_cheapest = fields.Boolean(
        string='Add cheapest eligible carrier on confirming backend quotations', default=False,
    )


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _tl_rate_carriers(self, carriers):
        """Return (carrier, price, success, note) per eligible method.

        Prices come from Odoo `rate_shipment`: it includes the provider implementation,
        weight/volume rules and provider-specific adjustments. No fabricated rates.
        """
        self.ensure_one()
        results = []
        for carrier in carriers.filtered('active'):
            if carrier.company_id and carrier.company_id != self.company_id:
                continue
            try:
                if not carrier._match(self.partner_shipping_id, self):
                    continue
                with self.env.cr.savepoint():
                    result = carrier.rate_shipment(self)
                success = bool(result.get('success'))
                price = result.get('price') or 0.0
                if price < 0:
                    success = False
                results.append((carrier, float(price), success,
                                result.get('error_message') or result.get('warning_message') or ''))
            except Exception as exc:  # provider-specific network errors should not hide other quotes
                _logger.warning('Carrier quote failed: %s (%s)', carrier.display_name, exc)
                results.append((carrier, 0.0, False, str(exc)[:200]))
        return sorted(results, key=lambda row: (not row[2], row[1], row[0].sequence, row[0].id))

    def _tl_best_carrier(self, carriers):
        self.ensure_one()
        return next((row for row in self._tl_rate_carriers(carriers) if row[2]), False)

    def _get_preferred_delivery_method(self, available_delivery_methods):
        # Native Odoo 20 website_sale extension point: preserve manual choice only
        # when the preference is disabled. Otherwise choose the cheapest rate.
        self.ensure_one()
        if self.website_id and self.company_id.tl_auto_web_cheapest:
            best = self._tl_best_carrier(available_delivery_methods)
            if best:
                return best[0]
        return super()._get_preferred_delivery_method(available_delivery_methods)

    def action_confirm(self):
        for order in self:
            if (order.state in ('draft', 'sent') and not order.website_id
                    and not order.carrier_id and order.company_id.tl_auto_sale_cheapest):
                carriers = self.env['delivery.carrier'].search([
                    ('active', '=', True),
                    '|', ('company_id', '=', False), ('company_id', '=', order.company_id.id),
                ])
                best = order._tl_best_carrier(carriers)
                if best:
                    order.set_delivery_line(best[0], best[1])
        return super().action_confirm()

    def action_tl_compare_carriers(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Compare carriers before confirming the order.'))
        return {'type': 'ir.actions.act_window', 'name': _('Compare carrier rates'),
                'res_model': 'tl.sale.carrier.compare.wizard', 'view_mode': 'form',
                'target': 'new', 'context': {'default_order_id': self.id}}
