# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleManufacturedFor(WebsiteSale):
    @http.route()
    def product(self, product, pricelist=None, **kwargs):
        user = request.env.user
        partner = user.partner_id if not user._is_public() else request.env["res.partner"]
        if not product.sudo()._website_manufactured_accessible(partner):
            raise NotFound()
        return super().product(product, pricelist=pricelist, **kwargs)

    @http.route()
    def product_document(self, product_template, document_id):
        user = request.env.user
        partner = user.partner_id if not user._is_public() else request.env["res.partner"]
        if not product_template.sudo()._website_manufactured_accessible(partner):
            raise NotFound()
        return super().product_document(product_template, document_id)
