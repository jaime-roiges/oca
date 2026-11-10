# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = "stock.move"

    tl_blanket_line_id = fields.Many2one(
        "sale.blanket.order.line", string="Blanket contract stock", copy=False,
        check_company=True, index=True,
    )
    tl_auto_allocation_picking_id = fields.Many2one(
        "stock.picking", string="Dedicated transfer from receipt", copy=False,
        readonly=True,
    )

    def _action_done(self, *args, **kwargs):
        # Deny accidental non-contract direct deliveries from protected locations.
        for move in self:
            protected = move.location_id.tl_blanket_line_id
            if protected:
                if move.tl_blanket_line_id != protected:
                    raise UserError(_("This stock is dedicated to another blanket contract."))
                if (move.location_dest_id.usage == "customer" and
                        move.sale_line_id.blanket_order_line != protected):
                    raise UserError(_("A customer delivery must consume the assigned blanket line."))
        result = super()._action_done(*args, **kwargs)
        # Receiving a linked PO *proposes* an internal transfer; warehouse staff
        # still confirm the move by PDA. The confirmed internal transfer reserves
        # stock in the ordinary location while awaiting that validation.
        incoming = self.filtered(
            lambda m: m.state == "done" and m.purchase_line_id and
            m.picking_type_id.code == "incoming" and
            m.purchase_line_id.order_id.tl_blanket_order_id and
            not m.tl_auto_allocation_picking_id and m.quantity > 0
        )
        for move in incoming:
            agreement = move.purchase_line_id.order_id.tl_blanket_order_id
            lines = agreement.line_ids.filtered(
                lambda line: line.product_id == move.product_id and
                line.tl_dedicated_warehouse_id and line.product_id.is_storable
            )
            if len(lines) != 1:
                continue  # Ambiguous -> manual allocation, no silent wrong reservation.
            line = lines[0]
            warehouse = line.tl_dedicated_warehouse_id
            if not move.location_dest_id._child_of(warehouse.lot_stock_id):
                continue  # Multistep receipt: allocate after regular put-away.
            location = line._tl_get_or_create_dedicated_location()
            pick = line._tl_create_stock_transfer(
                source=move.location_dest_id, destination=location,
                qty=move.quantity, uom=move.uom_id,
                origin="%s / %s" % (move.picking_id.name, agreement.name),
            )
            move.tl_auto_allocation_picking_id = pick.id
        return result


class BlanketLine(models.Model):
    _inherit = "sale.blanket.order.line"

    def _tl_create_stock_transfer(self, source, destination, qty, uom, origin):
        self.ensure_one()
        warehouse = self.tl_dedicated_warehouse_id
        if not warehouse or not warehouse.int_type_id:
            raise UserError(_("Configure an internal picking type for the warehouse."))
        if qty <= 0 or source == destination:
            raise UserError(_("Invalid quantity or stock locations."))
        picking = self.env["stock.picking"].create({
            "picking_type_id": warehouse.int_type_id.id,
            "company_id": self.company_id.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "origin": origin,
        })
        self.env["stock.move"].create({
            "name": self.product_id.display_name,
            "picking_id": picking.id,
            "company_id": self.company_id.id,
            "product_id": self.product_id.id,
            "product_uom_qty": qty,
            "uom_id": uom.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "tl_blanket_line_id": self.id,
        })
        picking.action_confirm()
        picking.action_assign()
        return picking
