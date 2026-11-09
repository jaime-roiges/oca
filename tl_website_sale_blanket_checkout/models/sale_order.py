# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _tl_check_unambiguous_contract(self, product):
        """A product with two eligible contracts must be selected explicitly.

        Regular website carts handle exactly one eligible blanket line, using
        the native OCA line auto-assignment. Multiple same-product agreements
        need the portal/manual contract line selection, never an arbitrary pick.
        """
        if not self.website_id or not self.partner_id or not product:
            return True
        partner = self.partner_id.commercial_partner_id
        matches = self.env["sale.blanket.order.line"].sudo().search([
            ("product_id", "=", product.id),
            ("partner_id", "child_of", partner.id),
            ("order_id.state", "=", "open"),
            ("company_id", "=", self.company_id.id),
            ("currency_id", "=", self.currency_id.id),
            ("remaining_uom_qty", ">", 0),
        ])
        if len(matches) > 1:
            raise UserError(_(
                "More than one active blanket contract covers this product. "
                "Request it through My Contracts, or ask a salesperson to select the contract."
            ))
        return True

    def _tl_validate_credit_checkout(self, visitor):
        self.ensure_one()
        if not visitor or visitor._is_public():
            raise AccessError(_("Sign in to place an order on credit."))
        commercial = visitor.partner_id.commercial_partner_id
        if (not commercial.skip_website_checkout_payment
                or commercial != self.partner_id.commercial_partner_id):
            raise AccessError(_("This customer is not authorized for credit checkout."))
        if not self.website_id or self.website_id.company_id != self.company_id:
            raise AccessError(_("Shopping cart does not belong to this website/company."))
        self._tl_validate_manufactured_products()
        for line in self.order_line.filtered(lambda x: x.product_id and not x.display_type):
            self._tl_check_unambiguous_contract(line.product_id)
        return True

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        if self.website_id and quantity > 0:
            product = self.env["product.product"].browse(int(product_id)).exists()
            if product:
                self._tl_check_unambiguous_contract(product)
        return super()._cart_add(product_id, quantity=quantity, uom_id=uom_id, **kwargs)

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        if self.website_id and quantity > 0:
            line = self.order_line.filtered(lambda x: x.id == line_id)
            if line:
                self._tl_check_unambiguous_contract(line.product_id)
        return super()._cart_update_line_quantity(line_id, quantity, **kwargs)

    def action_confirm(self):
        for order in self.filtered("website_id"):
            order._tl_validate_manufactured_products()
            for line in order.order_line.filtered(lambda x: x.product_id and not x.display_type):
                order._tl_check_unambiguous_contract(line.product_id)
        return super().action_confirm()
