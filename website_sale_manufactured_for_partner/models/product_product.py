# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models
from odoo.http import request

from .visibility import allowed_partner_ids


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _website_manufactured_accessible(self, partner):
        self.ensure_one()
        permitted = self.manufactured_for_partner_ids
        return not permitted or bool(set(permitted.ids) & set(allowed_partner_ids(partner)))

    def _is_add_to_cart_allowed(self):
        # Core 20.0 calls this from /shop/product/is_add_to_cart_allowed.
        result = super()._is_add_to_cart_allowed()
        if not result:
            return result
        try:
            visitor = request.env.user
            partner = (
                visitor.partner_id if not visitor._is_public() else self.env["res.partner"]
            )
        except RuntimeError:
            # Outside HTTP, the core method still works and checkout action_confirm
            # performs the authoritative customer check.
            return result
        return self._website_manufactured_accessible(partner)
