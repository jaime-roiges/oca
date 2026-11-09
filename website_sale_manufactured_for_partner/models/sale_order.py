# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .visibility import commercial_customer_matches


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _tl_website_visitor(self):
        """Resolve the real portal visitor even if Odoo handles the cart in sudo."""
        try:
            user = request.env.user
            if not user._is_internal():
                return user
        except RuntimeError:
            pass
        return False

    def _tl_validate_manufactured_products(self):
        """Central authority for backend, XML-RPC, portal and website confirmation."""
        for order in self:
            visitor = order._tl_website_visitor() if order.website_id else False
            if visitor and not visitor._is_public():
                if not commercial_customer_matches(visitor.partner_id, order.partner_id):
                    raise AccessError(_("This customer account cannot confirm this order."))
            for line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
                product = line.product_id
                if visitor:
                    # The real visitor is authoritative for website orders. A
                    # contact may have individual permission while the invoice
                    # address belongs to the same commercial company.
                    buyer = (
                        visitor.partner_id if not visitor._is_public()
                        else self.env["res.partner"]
                    )
                else:
                    buyer = order.partner_id
                if not product._website_manufactured_accessible(buyer):
                    raise ValidationError(
                        _("A product in this order is not authorized for this customer.")
                    )
        return True

    def _tl_check_cart_product(self, product):
        self.ensure_one()
        if not self.website_id:
            return
        visitor = self._tl_website_visitor()
        partner = (
            visitor.partner_id if visitor and not visitor._is_public()
            else self.env["res.partner"]
        )
        if not product or not product._website_manufactured_accessible(partner):
            raise AccessError(_("This product is not available for your customer account."))
        if visitor and not visitor._is_public() and not commercial_customer_matches(
            partner, self.partner_id
        ):
            raise AccessError(_("Your order belongs to a different customer account."))

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        if self.website_id and quantity > 0:
            product = self.env["product.product"].browse(int(product_id)).exists()
            self._tl_check_cart_product(product)
        return super()._cart_add(product_id, quantity=quantity, uom_id=uom_id, **kwargs)

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        if self.website_id and quantity > 0:
            line = self.order_line.filtered(lambda l: l.id == line_id)
            if line:
                self._tl_check_cart_product(line.product_id)
        return super()._cart_update_line_quantity(line_id, quantity, **kwargs)

    def action_confirm(self):
        self._tl_validate_manufactured_products()
        return super().action_confirm()

    def write(self, vals):
        result = super().write(vals)
        if "partner_id" in vals:
            self.filtered(lambda order: order.state in ("sale", "done"))._tl_validate_manufactured_products()
        return result
