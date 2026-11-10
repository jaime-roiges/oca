# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from ..models.product_template import _tl_contract_availability_rows


class WebsiteBlanketContracts(http.Controller):
    @staticmethod
    def _visible_line(line_id):
        user = request.env.user
        if user._is_public():
            raise Forbidden()
        try:
            record_id = int(line_id)
        except (TypeError, ValueError):
            raise NotFound() from None
        website = request.website
        candidates = request.env["sale.blanket.order.line"]._tl_website_candidates(
            request.env["sale.blanket.order.line"].sudo().browse(record_id).product_id,
            user.partner_id, website.company_id, request.pricelist.currency_id,
        )
        line = candidates.filtered(lambda x: x.id == record_id)
        if not line:
            raise NotFound()
        return line

    @http.route("/shop/blanket/contract/<int:line_id>", type="http", website=True, auth="user")
    def contract_choice(self, line_id, **kwargs):
        line = self._visible_line(line_id)
        product = line.product_id.with_context(website_id=request.website.id)
        options = []
        for uom in product._get_available_uoms() - request.website.restricted_uom_ids:
            details = _tl_contract_availability_rows(
                line, request.env.lang, selected_uom=uom, product=product,
            )[0]
            options.append(details)
        return request.render("tl_website_sale_blanket_contract.contract_purchase_form", {
            "agreement_line": line,
            "max_qty": line.remaining_uom_qty,
            "packaging_options": options,
        })

    @http.route("/shop/blanket/contract/add", type="http", website=True,
                auth="user", methods=["POST"], csrf=True)
    def contract_add(self, line_id=None, quantity=None, uom_id=None, **kwargs):
        line = self._visible_line(line_id)
        try:
            qty = float(quantity)
            unit_id = int(uom_id) if uom_id else line.product_uom.id
        except (TypeError, ValueError):
            raise BadRequest() from None
        if not (0 < qty < 1e12):
            raise BadRequest()
        product = line.product_id.with_context(website_id=request.website.id)
        allowed_uoms = product._get_available_uoms() - request.website.restricted_uom_ids
        unit = allowed_uoms.filtered(lambda rec: rec.id == unit_id)
        if len(unit) != 1:
            raise BadRequest()
        order = request.website.sale_get_order(force_create=True)
        if not order or order.partner_id.commercial_partner_id != request.env.user.partner_id.commercial_partner_id:
            raise Forbidden()
        try:
            order._cart_add(
                line.product_id.id, quantity=qty,
                uom_id=unit.id,
                tl_blanket_line_id=line.id,
            )
        except (UserError, AccessError):
            return request.redirect("/shop/blanket/contract/%s" % line.id)
        return request.redirect("/shop/cart")
