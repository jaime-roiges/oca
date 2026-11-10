# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _verify_updated_quantity(self, order_line, product_id, new_qty, uom_id, **kwargs):
        """For contracted products check the *dedicated* stock, not WH/Stock.

        The website core's global availability test deliberately ignores
        separate internal locations outside the normal warehouse stock node.
        Never bypass it for ordinary products. The contractual balance is
        independently validated by tl_website_sale_blanket_contract.
        """
        if not self.website_id or new_qty <= 0:
            return super()._verify_updated_quantity(
                order_line, product_id, new_qty, uom_id, **kwargs
            )
        product = self.env["product.product"].browse(product_id).exists()
        uom = self.env["uom.uom"].browse(uom_id).exists()
        if not product or not uom:
            return super()._verify_updated_quantity(
                order_line, product_id, new_qty, uom_id, **kwargs
            )
        contract = self._tl_select_web_blanket(
            product, new_qty, uom,
            explicit_id=kwargs.get("tl_blanket_line_id") or (
                order_line.blanket_order_line.id if order_line else None
            ),
            existing=order_line,
        )
        if not contract or not contract.tl_dedicated_location_id:
            return super()._verify_updated_quantity(
                order_line, product_id, new_qty, uom_id, **kwargs
            )
        if self.warehouse_id != contract.tl_dedicated_warehouse_id:
            raise UserError(_("Contract stock belongs to a different warehouse."))
        # Physical availability is expressed in the agreement line's UoM.
        wanted = uom._compute_quantity(new_qty, contract.product_uom, round=False)
        available = contract.tl_dedicated_available_qty
        if contract.product_uom.compare(wanted, available) > 0:
            raise UserError(_(
                "Only %(available)s units are physically available for this contract.",
                available=available,
            ))
        return new_qty, ""
