# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import UserError


class AllocateStockWizard(models.TransientModel):
    _name = "tl.sale.blanket.stock.allocate.wizard"
    _description = "Allocate stock to a blanket contract"

    blanket_line_id = fields.Many2one("sale.blanket.order.line", required=True)
    source_location_id = fields.Many2one(
        "stock.location", string="From location", required=True,
        domain="[('usage','=','internal')]",
    )
    qty = fields.Float(string="Quantity", required=True, digits="Product Unit")
    uom_id = fields.Many2one("uom.uom", related="blanket_line_id.product_uom")

    def action_allocate(self):
        self.ensure_one()
        line = self.blanket_line_id
        warehouse = line.tl_dedicated_warehouse_id
        if not warehouse or not self.source_location_id._child_of(warehouse.lot_stock_id):
            raise UserError(_("Choose a source location inside the warehouse's regular stock."))
        if line.product_uom.compare(self.qty, 0) <= 0:
            raise UserError(_("Quantity must be positive."))
        target = line._tl_get_or_create_dedicated_location()
        picking = line._tl_create_stock_transfer(
            self.source_location_id, target, self.qty, line.product_uom,
            "Blanket %s / %s" % (line.order_id.name, line.product_id.display_name),
        )
        return {
            "type": "ir.actions.act_window", "res_model": "stock.picking",
            "res_id": picking.id, "view_mode": "form",
        }
