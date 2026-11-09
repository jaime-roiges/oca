# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from math import isfinite
from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request
from odoo.tools import float_compare


class SupplyBlanketPortal(http.Controller):
    def _contract_domain(self):
        commercial = request.env.user.partner_id.commercial_partner_id
        company = request.website.company_id
        return [
            ("tl_portal_visible", "=", True),
            ("state", "=", "open"),
            ("partner_id", "child_of", commercial.id),
            ("company_id", "=", company.id),
        ]

    def _contract(self, contract_id):
        if request.env.user._is_public():
            raise Forbidden()
        # OCA blanket order has no portal ACL. Elevated search is strictly
        # scoped by website company and user's commercial parent company.
        contract = request.env["sale.blanket.order"].sudo().search(
            [("id", "=", contract_id), *self._contract_domain()], limit=1
        )
        if not contract:
            raise NotFound()
        return contract

    @http.route("/my/contracts", type="http", auth="user", website=True)
    def list_blankets(self, **kwargs):
        contracts = request.env["sale.blanket.order"].sudo().search(
            self._contract_domain(), order="id desc"
        )
        return request.render("tl_sale_blanket_portal.portal_contracts", {
            "contracts": contracts, "page_name": "tl_contracts",
        })

    @http.route("/my/contracts/<int:contract_id>", type="http", auth="user", website=True)
    def detail(self, contract_id, **kwargs):
        contract = self._contract(contract_id)
        advances = request.env["tl.sale.advance"].sudo().search([
            ("blanket_order_id", "=", contract.id),
            ("kind", "=", "customer"), ("invoice_id.state", "=", "posted"),
        ])
        release_requests = request.env["tl.sale.release.request"].sudo().search([
            ("blanket_order_id", "=", contract.id),
            ("partner_id", "child_of", request.env.user.partner_id.commercial_partner_id.id),
        ], limit=30, order="id desc")
        return request.render("tl_sale_blanket_portal.portal_contract_detail", {
            "contract": contract,
            "contract_lines": contract.line_ids.filtered(lambda l: l.product_id and not l.display_type),
            "advance_base": sum(advances.mapped("amount_base")),
            "advance_paid_base": sum(a.amount_base for a in advances if a.payment_state == "paid"),
            "advance_applied": sum(advances.mapped("amount_applied")),
            "advance_remaining": sum(a.amount_remaining for a in advances if a.payment_state == "paid"),
            "release_requests": release_requests,
            "page_name": "tl_contract_detail",
        })

    @http.route("/my/contracts/<int:contract_id>/request", type="http",
                auth="user", website=True, methods=["POST"], csrf=True)
    def request_release(self, contract_id, line_id=None, quantity=None, notes=None, **kwargs):
        contract = self._contract(contract_id)
        try:
            line_id, qty = int(line_id), float(quantity)
        except (ValueError, TypeError):
            raise Forbidden() from None
        line = contract.line_ids.filtered(lambda l: l.id == line_id and not l.display_type)
        if len(line) != 1 or not isfinite(qty):
            raise Forbidden()
        precision = request.env["decimal.precision"].precision_get("Product Unit")
        if (float_compare(qty, 0, precision_digits=precision) <= 0
                or float_compare(qty, line.remaining_uom_qty, precision_digits=precision) > 0):
            raise Forbidden()
        request.env["tl.sale.release.request"].sudo().create({
            "blanket_order_id": contract.id,
            "line_id": line.id,
            "partner_id": request.env.user.partner_id.id,
            "quantity": qty,
            "notes": (notes or "")[:1000],
        })
        return request.redirect("/my/contracts/%s" % contract.id)
