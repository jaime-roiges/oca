# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        # Serialize checks against a contract line even when two backoffice
        # workers confirm separate orders at the same instant.
        blanket_lines = self.order_line.mapped("blanket_order_line").filtered(
            "tl_dedicated_location_id"
        )
        if blanket_lines:
            self.env.cr.execute(
                "SELECT id FROM sale_blanket_order_line WHERE id IN %s ORDER BY id FOR UPDATE",
                [tuple(sorted(blanket_lines.ids))],
            )
        for order in self:
            required_by_agreement = {}
            for line in order.order_line.filtered("blanket_order_line"):
                agreement = line.blanket_order_line
                if agreement.tl_dedicated_warehouse_id and not agreement.tl_dedicated_location_id:
                    raise UserError(_(
                        "Move the contracted goods into its dedicated location before confirming."
                    ))
                if not agreement.tl_dedicated_location_id:
                    continue
                if order.warehouse_id != agreement.tl_dedicated_warehouse_id:
                    raise UserError(_("Choose the contract warehouse to deliver dedicated stock."))
                if not line.product_id.is_storable:
                    raise UserError(_("Only storable items can use dedicated contract stock."))
                qty = line.product_uom_id._compute_quantity(
                    line.product_uom_qty, agreement.product_uom, round=False
                )
                required_by_agreement[agreement] = required_by_agreement.get(agreement, 0) + qty
            for agreement, qty in required_by_agreement.items():
                if agreement.product_uom.compare(qty, agreement.tl_dedicated_available_qty) > 0:
                    raise UserError(_("Insufficient dedicated stock for contract %(name)s.",
                                      name=agreement.order_id.name))
        return super().action_confirm()
