# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Authenticated customer portal for OCA sale.blanket.order.

Contract visibility is always scoped to the website company and the signed-in
commercial partner. Never accept a partner/company ID from URL parameters.
"""
from math import ceil, isfinite
from werkzeug.exceptions import Forbidden, NotFound

from odoo import _, http
from odoo.http import request
from odoo.tools import float_compare, float_round


STATUS_OPTIONS = ("open", "cancelled", "done", "expired", "all")
PAGE_SIZE = 30


def status_domain(status):
    """Return the server-side Odoo domain for a whitelisted status."""
    return {
        "open": [("state", "=", "open"), ("tl_portal_cancelled", "=", False)],
        "cancelled": [("tl_portal_cancelled", "=", True)],
        "done": [("state", "=", "done"), ("tl_portal_cancelled", "=", False)],
        "expired": [("state", "=", "expired"), ("tl_portal_cancelled", "=", False)],
        "all": [],
    }.get(status, [("state", "=", "open"), ("tl_portal_cancelled", "=", False)])


def line_consumption(line, precision_digits=2):
    """Distinguish confirmed contract usage from draft quotations and carts.

    OCA's ordered_uom_qty includes draft/sent orders; the portal intentionally
    uses only confirmed sale orders for its 'consumed' percentage. UoM values
    are converted into the blanket line's product_uom before summing.
    """
    consumed = draft = 0.0
    for sale_line in line.sale_lines:
        if sale_line.product_id != line.product_id:
            continue
        state = sale_line.order_id.state
        if (state not in ("sale", "done", "draft", "sent")
                or not sale_line.product_uom_id or not line.product_uom):
            continue
        quantity = sale_line.product_uom_id._compute_quantity(
            sale_line.product_uom_qty, line.product_uom
        )
        if state in ("sale", "done"):
            consumed += quantity
        else:
            draft += quantity
    consumed = float_round(consumed, precision_digits=precision_digits)
    draft = float_round(draft, precision_digits=precision_digits)
    contracted = line.original_uom_qty
    percentage = consumed / contracted * 100.0 if contracted > 0 else 0.0
    return {
        "consumed": consumed,
        "draft": draft,
        "percentage": percentage,
        "percentage_display": "%.1f%%" % percentage,
        "progress_width": max(0.0, min(100.0, percentage)),
    }


class SupplyBlanketPortal(http.Controller):
    def _contract_domain(self):
        commercial = request.env.user.partner_id.commercial_partner_id
        company = request.website.company_id
        return [
            ("tl_portal_visible", "=", True),
            ("confirmed", "=", True),
            ("partner_id", "child_of", commercial.id),
            ("company_id", "=", company.id),
        ]

    def _contract(self, contract_id):
        if request.env.user._is_public():
            raise Forbidden()
        contract = request.env["sale.blanket.order"].sudo().search(
            [("id", "=", contract_id), *self._contract_domain()], limit=1
        )
        if not contract:
            raise NotFound()
        return contract

    def _status_labels(self):
        return {
            "draft": _("Borrador"),
            "open": _("Abierto"),
            "done": _("Completado"),
            "expired": _("Caducado"),
            "cancelled": _("Cancelado"),
        }

    @http.route("/my/contracts", type="http", auth="user", website=True)
    def list_blankets(self, status="open", product_id=None, page=1, **kwargs):
        status = status if status in STATUS_OPTIONS else "open"
        try:
            product_id = int(product_id or 0)
            page = max(1, int(page))
        except (TypeError, ValueError, OverflowError):
            product_id, page = 0, 1
        product_id = max(product_id, 0)
        contract_model = request.env["sale.blanket.order"].sudo()
        base_domain = self._contract_domain()
        # Selectable products must be derived from visible contracts only.
        products = contract_model.search(base_domain).mapped("line_ids.product_id")
        products = products.sorted(key=lambda product: (product.display_name or "").lower())
        domain = base_domain + status_domain(status)
        if product_id:
            domain.append(("line_ids.product_id", "=", product_id))
        count = contract_model.search_count(domain)
        pages = max(1, ceil(count / PAGE_SIZE))
        page = min(page, pages)
        contracts = contract_model.search(
            domain, order="id desc", offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE
        )
        labels = self._status_labels()
        return request.render("tl_sale_blanket_portal.portal_contracts", {
            "contracts": contracts,
            "status": status,
            "product_id": product_id,
            "products": products,
            "status_choices": [
                ("open", _("Abiertos")),
                ("cancelled", _("Cancelados")),
                ("done", _("Completados")),
                ("expired", _("Caducados")),
                ("all", _("Todos")),
            ],
            "status_labels": labels,
            "page": page,
            "contract_statuses": {
                c.id: labels["cancelled" if c.tl_portal_cancelled else c.state]
                for c in contracts
            },
            "contract_products": {
                c.id: ", ".join(
                    c.line_ids.filtered(lambda line: line.product_id and not line.display_type)
                    .mapped("product_id.display_name")[:4]
                ) for c in contracts
            },
            "pages": pages,
            "total_contracts": count,
            "page_name": "tl_contracts",
        })

    @http.route("/my/contracts/<int:contract_id>", type="http", auth="user", website=True)
    def detail(self, contract_id, product_id=None, **kwargs):
        contract = self._contract(contract_id)
        advances = request.env["tl.sale.advance"].sudo().search([
            ("blanket_order_id", "=", contract.id),
            ("kind", "=", "customer"), ("invoice_id.state", "=", "posted"),
        ])
        release_requests = request.env["tl.sale.release.request"].sudo().search([
            ("blanket_order_id", "=", contract.id),
            ("partner_id", "child_of", request.env.user.partner_id.commercial_partner_id.id),
        ], limit=30, order="id desc")
        all_lines = contract.line_ids.filtered(lambda line: line.product_id and not line.display_type)
        products = all_lines.mapped("product_id").sorted(
            key=lambda product: (product.display_name or "").lower()
        )
        try:
            selected_product_id = max(0, int(product_id or 0))
        except (TypeError, ValueError, OverflowError):
            selected_product_id = 0
        lines = (all_lines.filtered(lambda line: line.product_id.id == selected_product_id)
                 if selected_product_id else all_lines)
        precision = request.env["decimal.precision"].precision_get("Product Unit")
        usage = {line.id: line_consumption(line, precision) for line in lines}
        labels = self._status_labels()
        return request.render("tl_sale_blanket_portal.portal_contract_detail", {
            "contract": contract,
            "contract_lines": lines,
            "line_products": products,
            "selected_product_id": selected_product_id,
            "line_usage": usage,
            "contract_status": labels["cancelled" if contract.tl_portal_cancelled else contract.state],
            "can_request": contract.state == "open" and not contract.tl_portal_cancelled,
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
        if contract.state != "open" or contract.tl_portal_cancelled:
            raise Forbidden()
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
