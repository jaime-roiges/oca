# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class SaleBlanketOrderLine(models.Model):
    _inherit = "sale.blanket.order.line"

    @api.model
    def _tl_website_candidates(self, product, partner, company, currency):
        """Find eligible lines in the requested company, *never* all contracts.

        Caller supplies the authenticated visitor/validated cart partner, not a
        partner id taken from HTTP parameters. Portal and internal company
        contacts use the same commercial partner's contracts.
        """
        empty = self.browse()
        if not (product and partner and company and currency):
            return empty
        today = fields.Date.context_today(self)
        commercial = partner.commercial_partner_id
        return self.sudo().search([
            ("product_id", "=", product.id),
            ("partner_id", "in", [commercial.id, partner.id]),
            ("company_id", "=", company.id),
            ("currency_id", "=", currency.id),
            ("order_id.state", "=", "open"),
            ("order_id.validity_start_date", "<=", today),
            ("order_id.validity_date", ">=", today),
        ], order="id")

    def _tl_available_for_sale_line(self, requested_qty, uom, current_line=None):
        """Check availability in blanket line UoM, restoring the cart's own qty.

        OCA's remaining_uom_qty counts draft carts. When changing a cart line
        we first add back its existing demand to avoid a false shortage.
        """
        self.ensure_one()
        wanted = uom._compute_quantity(requested_qty, self.product_uom, round=False)
        remaining = self.remaining_uom_qty
        if current_line and current_line.blanket_order_line == self:
            remaining += current_line.product_uom_id._compute_quantity(
                current_line.product_uom_qty, self.product_uom, round=False
            )
        return self.product_uom.compare(wanted, remaining) <= 0

    def _tl_price_for_uom(self, uom):
        self.ensure_one()
        return self.product_uom._compute_price(self.price_unit, uom)
