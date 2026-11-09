# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.addons.website_sale_checkout_skip_payment.controllers.main import (
    CheckoutSkipPaymentWebsite,
)


class SupplyCreditCheckout(CheckoutSkipPaymentWebsite):
    @http.route()
    def shop_payment_confirmation(self, **post):
        website = request.env.website
        if not website.checkout_skip_payment:
            return super().shop_payment_confirmation(**post)
        order_id = request.session.get("sale_last_order_id")
        if not order_id:
            return super().shop_payment_confirmation(**post)
        order = request.env["sale.order"].sudo().browse(order_id).exists()
        if (
            not order or order.website_id != website
            or order.partner_id.commercial_partner_id
                != request.env.user.partner_id.commercial_partner_id
        ):
            raise Forbidden()
        if order.state == "sale":
            return request.render(
                "website_sale.confirmation",
                self._prepare_shop_payment_confirmation_values(order),
            )
        try:
            order._tl_validate_credit_checkout(request.env.user)
        except (AccessError, UserError, ValidationError):
            return request.render("tl_website_sale_blanket_checkout.checkout_denied")
        # An URL typed directly must not bypass required address, delivery,
        # extra-information or terms steps. This is the core 20.0 validator.
        redirect = request.env["website.checkout.step"].validate_checkout_progress(
            "/shop/payment/transaction", order
        )
        if redirect:
            return request.redirect(redirect)
        return super().shop_payment_confirmation(**post)
