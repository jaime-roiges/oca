# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import UserError


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _get_stock_move_values(
        self, product_id, product_qty, uom_id, location_dest_id,
        name, origin, company_id, values,
    ):
        move_values = super()._get_stock_move_values(
            product_id, product_qty, uom_id, location_dest_id,
            name, origin, company_id, values,
        )
        sale_line_id = values.get("sale_line_id")
        if not sale_line_id:
            return move_values
        sale_line = self.env["sale.order.line"].browse(sale_line_id).exists()
        agreement = sale_line.blanket_order_line
        dedicated = agreement.tl_dedicated_location_id
        if not dedicated:
            return move_values
        warehouse = sale_line.order_id.warehouse_id
        if warehouse != agreement.tl_dedicated_warehouse_id:
            raise UserError(_("The sales warehouse differs from the contract stock warehouse."))
        if sale_line.product_id != agreement.product_id:
            raise UserError(_("Contract product and sale product must match."))
        # Only change the earliest move sourcing physical stock. Other moves in
        # pack/ship chains must preserve their regular source/output locations.
        if self.location_src_id == warehouse.lot_stock_id:
            move_values.update({
                "location_id": dedicated.id,
                "tl_blanket_line_id": agreement.id,
            })
        return move_values
