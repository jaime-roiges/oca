# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models
from odoo.fields import Domain
from odoo.http import request

from .visibility import allowed_partner_ids


class Website(models.Model):
    _inherit = "website"

    def sale_product_domain(self):
        domain = super().sale_product_domain()
        try:
            user = request.env.user
        except RuntimeError:
            user = self.env.user
        # Neither public visitors nor their delivery-address selections may
        # disclose customer-exclusive products.
        partner = user.partner_id if not user._is_public() else self.env["res.partner"]
        permitted = allowed_partner_ids(partner)
        visibility = Domain.OR([
            Domain("website_manufactured_restricted", "=", False),
            Domain("website_manufactured_for_partner_ids", "in", permitted),
        ])
        return Domain.AND([Domain(domain), visibility])
