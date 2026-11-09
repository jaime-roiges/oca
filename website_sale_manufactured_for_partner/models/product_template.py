# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.http import request

from .visibility import allowed_partner_ids


class ProductTemplate(models.Model):
    _inherit = "product.template"

    website_manufactured_restricted = fields.Boolean(
        compute="_compute_website_manufactured_visibility",
        store=True,
        index=True,
        help="One or more variants are reserved for named customers.",
    )
    website_manufactured_for_partner_ids = fields.Many2many(
        "res.partner",
        relation="product_tmpl_website_manuf_partner_rel",
        column1="product_tmpl_id",
        column2="partner_id",
        compute="_compute_website_manufactured_visibility",
        store=True,
        string="Website allowed customers",
    )

    @api.depends("product_variant_ids", "product_variant_ids.manufactured_for_partner_ids")
    def _compute_website_manufactured_visibility(self):
        for template in self:
            permitted = template.product_variant_ids.mapped("manufactured_for_partner_ids")
            template.website_manufactured_restricted = bool(permitted)
            template.website_manufactured_for_partner_ids = [(6, 0, permitted.ids)]

    def _website_manufactured_accessible(self, partner):
        self.ensure_one()
        if not self.website_manufactured_restricted:
            return True
        return bool(
            set(self.website_manufactured_for_partner_ids.ids)
            & set(allowed_partner_ids(partner))
        )

    def _get_combination_info(self, *args, **kwargs):
        info = super()._get_combination_info(*args, **kwargs)
        if not info.get("product_id"):
            return info
        try:
            visitor = request.env.user
        except RuntimeError:
            return info
        partner = (
            visitor.partner_id if not visitor._is_public() else self.env["res.partner"]
        )
        product = self.env["product.product"].sudo().browse(info["product_id"])
        if not product._website_manufactured_accessible(partner):
            raise AccessError(self.env._("This product variant is not available to your customer account."))
        return info
