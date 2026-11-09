# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from math import isfinite

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http
from odoo.http import request
from odoo.tools import float_compare


class DimpalBlanketPortal(http.Controller):
    def _domain(self):
        return [
            ('order_type', '=', 'blanket'),
            ('dimpal_portal_visible', '=', True),
            ('state', '=', 'sale'),
            ('partner_id', 'child_of', request.env.user.partner_id.commercial_partner_id.id),
        ]

    def _blanket(self, order_id):
        # The portal sale.order ACL and the commercial partner domain BOTH apply.
        order = request.env['sale.order'].search([('id', '=', order_id), *self._domain()], limit=1)
        if not order:
            raise NotFound()
        order.check_access('read')
        return order

    @http.route('/my/dimpal/contracts', type='http', auth='user', website=True)
    def list_blankets(self, **kwargs):
        orders = request.env['sale.order'].search(self._domain(), order='id desc')
        return request.render('tl_dimpal_portal_blanket.portal_contracts', {
            'contracts': orders, 'page_name': 'dimpal_contracts',
        })

    @http.route('/my/dimpal/contracts/<int:contract_id>', type='http', auth='user', website=True)
    def detail(self, contract_id, **kwargs):
        blanket = self._blanket(contract_id)
        # Invoices are accounting documents. Elevation is deliberately restricted
        # to the explicitly authorized blanket and outgoing (customer) advances.
        advances = request.env['tl.dimpal.advance'].sudo().search([
            ('blanket_order_id', '=', blanket.id), ('kind', '=', 'customer'),
            ('invoice_id.state', '=', 'posted'),
        ])
        release_requests = request.env['tl.dimpal.release.request'].sudo().search([
            ('blanket_order_id', '=', blanket.id),
            ('partner_id', 'child_of', request.env.user.partner_id.commercial_partner_id.id),
        ], limit=30, order='id desc')
        return request.render('tl_dimpal_portal_blanket.portal_contract_detail', {
            'contract': blanket,
            'contract_lines': blanket.order_line.filtered(lambda l: l.product_id and not l.display_type).sudo(),
            'advance_base': sum(advances.mapped('amount_base')),
            'advance_paid_base': sum(a.amount_base for a in advances if a.payment_state == 'paid'),
            'advance_applied': sum(advances.mapped('amount_applied')),
            'advance_remaining': sum(a.amount_remaining for a in advances if a.payment_state == 'paid'),
            'release_requests': release_requests,
            'page_name': 'dimpal_contract_detail',
        })

    @http.route('/my/dimpal/contracts/<int:contract_id>/request', type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def request_release(self, contract_id, line_id=None, quantity=None, notes=None, **kwargs):
        blanket = self._blanket(contract_id)
        try:
            line_id, qty = int(line_id), float(quantity)
        except (ValueError, TypeError):
            raise Forbidden() from None
        line = blanket.order_line.filtered(lambda l: l.id == line_id and not l.display_type)
        if len(line) != 1 or not line.product_uom_id or not isfinite(qty):
            raise Forbidden()
        precision = line.product_uom_id.rounding or .01
        if (float_compare(qty, 0, precision_rounding=precision) <= 0
                or float_compare(qty, line.call_off_remaining_qty, precision_rounding=precision) > 0):
            raise Forbidden()
        # Controlled sudo ONLY after both sale.order ACL and ownership checks.
        request.env['tl.dimpal.release.request'].sudo().create({
            'blanket_order_id': blanket.id,
            'line_id': line.id,
            'partner_id': request.env.user.partner_id.id,
            'quantity': qty,
            'notes': (notes or '')[:1000],
        })
        return request.redirect('/my/dimpal/contracts/%s' % blanket.id)
