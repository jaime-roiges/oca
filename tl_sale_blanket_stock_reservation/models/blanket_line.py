# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BlanketLine(models.Model):
    _inherit = "sale.blanket.order.line"

    tl_dedicated_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Dedicated stock warehouse", check_company=True,
        help="Set for goods that must not be sold to other customers.",
    )
    tl_dedicated_location_id = fields.Many2one(
        "stock.location", string="Dedicated stock location", copy=False,
        check_company=True, readonly=True,
    )
    tl_dedicated_available_qty = fields.Float(
        string="Physically available (contract UoM)",
        compute="_compute_tl_dedicated_available_qty", digits="Product Unit",
    )

    @api.depends("tl_dedicated_location_id", "product_id", "product_uom")
    def _compute_tl_dedicated_available_qty(self):
        for line in self:
            if line.tl_dedicated_location_id and line.product_id and line.product_uom:
                qty = self.env["stock.quant"]._get_available_quantity(
                    line.product_id, line.tl_dedicated_location_id, strict=True
                )
                line.tl_dedicated_available_qty = line.product_id.uom_id._compute_quantity(
                    qty, line.product_uom, round=False
                )
            else:
                line.tl_dedicated_available_qty = 0.0

    def _tl_get_or_create_dedicated_location(self):
        self.ensure_one()
        if self.tl_dedicated_location_id:
            return self.tl_dedicated_location_id
        warehouse = self.tl_dedicated_warehouse_id
        if not warehouse or warehouse.company_id != self.company_id:
            raise UserError(_("Select a warehouse belonging to the agreement company."))
        if not self.product_id or not self.product_id.is_storable:
            raise UserError(_("Dedicated stock requires a storable product."))
        if self.order_id.state not in ("open", "done"):
            raise UserError(_("Confirm the contract before allocating stock."))
        # Serialize location creation, including repeated calls from 2 users.
        self.env.cr.execute(
            "SELECT id FROM sale_blanket_order_line WHERE id = %s FOR UPDATE", [self.id]
        )
        self.invalidate_recordset(["tl_dedicated_location_id"])
        if self.tl_dedicated_location_id:
            return self.tl_dedicated_location_id
        location = self.env["stock.location"].create({
            "name": "%s / %s / #%s" % (self.order_id.name, self.product_id.display_name, self.id),
            "location_id": warehouse.view_location_id.id,
            "usage": "internal",
            "company_id": self.company_id.id,
            "tl_blanket_line_id": self.id,
        })
        self.tl_dedicated_location_id = location
        return location

    def action_tl_allocate_stock(self):
        self.ensure_one()
        if not self.tl_dedicated_warehouse_id:
            raise UserError(_("Set a dedicated warehouse first."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "tl.sale.blanket.stock.allocate.wizard",
            "name": _("Move stock into the contract"),
            "view_mode": "form", "target": "new",
            "context": {"default_blanket_line_id": self.id},
        }

    @api.constrains("tl_dedicated_warehouse_id", "tl_dedicated_location_id")
    def _check_tl_dedicated_location(self):
        for line in self:
            warehouse = line.tl_dedicated_warehouse_id
            location = line.tl_dedicated_location_id
            if location and (
                not warehouse or location.company_id != line.company_id or
                location.tl_blanket_line_id != line or
                not location._child_of(warehouse.view_location_id) or
                location._child_of(warehouse.lot_stock_id)
            ):
                raise ValidationError(_("The dedicated location must be outside regular warehouse stock."))
