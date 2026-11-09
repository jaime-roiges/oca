# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _dimpal_active_blanket_for_product(self, product, partner):
        """Only the current client's active blanket orders are considered.

        No user-facing name, price or quantity is leaked from the matched contract.
        """
        self.ensure_one()
        if not product or not partner:
            return False
        blanket = self.env["sale.order"].sudo().search([
            ("order_type", "=", "blanket"),
            ("state", "=", "sale"),
            ("dimpal_portal_visible", "=", True),
            ("company_id", "=", self.company_id.id),
            ("partner_id", "child_of", partner.commercial_partner_id.id),
            ("order_line.product_id", "=", product.id),
        ])
        return any(
            line.product_id == product and not line.display_type
            and line.call_off_remaining_qty > 0
            for order in blanket for line in order.order_line
        )

    def _dimpal_check_website_contract_lines(self, product=None):
        """Shop payments, including skip-payment, must not consume blanket stock."""
        for order in self.filtered("website_id"):
            if order.order_type in ("blanket", "call_off"):
                raise UserError(_("Contract releases must be requested from the customer portal."))
            products = product or order.order_line.filtered(
                lambda line: line.product_id and not line.display_type
            ).mapped("product_id")
            for item in products:
                if order._dimpal_active_blanket_for_product(item, order.partner_id):
                    raise UserError(_(
                        "This product has an active supply contract. "
                        "Request its delivery in My Account / Supply Contracts."
                    ))
        return True

    def _dimpal_validate_credit_checkout(self, portal_user):
        self.ensure_one()
        if not portal_user or portal_user._is_public():
            raise AccessError(_("Sign in to place an order on credit."))
        commercial = portal_user.partner_id.commercial_partner_id
        if (
            not commercial.skip_website_checkout_payment
            or commercial != self.partner_id.commercial_partner_id
        ):
            raise AccessError(_("This customer is not authorized for credit checkout."))
        if not self.website_id or self.website_id.company_id != self.company_id:
            raise AccessError(_("The shopping cart is not valid for this website."))
        self._dimpal_validate_manufactured_products()
        self._dimpal_check_website_contract_lines()
        return True

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        if self.website_id and quantity > 0:
            item = self.env["product.product"].browse(int(product_id)).exists()
            if item:
                self._dimpal_check_website_contract_lines(item)
        return super()._cart_add(product_id, quantity=quantity, uom_id=uom_id, **kwargs)

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        if self.website_id and quantity > 0:
            line = self.order_line.filtered(lambda current: current.id == line_id)
            if line:
                self._dimpal_check_website_contract_lines(line.product_id)
        return super()._cart_update_line_quantity(line_id, quantity, **kwargs)

    def action_confirm(self):
        for order in self.filtered("website_id"):
            order._dimpal_check_website_contract_lines()
            if order.create_call_off_from_so_if_possible:
                order.create_call_off_from_so_if_possible = False
        return super().action_confirm()
