# Copyright 2014-2016 Numérigraphe SARL
# Copyright 2017 ForgeFlow, S.L.
# Copyright 2021 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import pytz

from odoo import models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _purchase_split_date_get_group_keys(self, picking=False):
        """Return the grouping key used to split incoming shipments by date."""
        self.ensure_one()
        tz = self.order_id.picking_type_id.warehouse_id.partner_id.tz
        wh_tz = pytz.timezone(tz) if tz else self.env.tz
        date_planned_tz = self.date_planned.astimezone(pytz.utc).astimezone(wh_tz)
        return (("date_planned", date_planned_tz.date()),)

    def _purchase_split_date_get_sorted_keys(self):
        """Return the key used to sort purchase lines before grouping."""
        self.ensure_one()
        return (self.date_planned,)

    def _create_stock_moves(self, picking=False):
        """Create moves and make Odoo 20 assign one picking per planned date.

        Odoo 20 creates purchase moves without a picking during initial PO
        confirmation and assigns the picking later from ``stock.move._action_confirm``.
        The context marker returned with the moves makes ``stock.move`` include the
        planned date in its picking grouping key.

        When core provides an existing picking (for example after editing a confirmed
        PO), keep the historical behaviour: reuse it only for lines matching its date
        and let the remaining moves be assigned to date-specific pickings.
        """
        if not picking:
            return super()._create_stock_moves(picking).with_context(
                purchase_delivery_split_date=True
            )

        moves = self.env["stock.move"]
        tz = picking.picking_type_id.warehouse_id.partner_id.tz
        order_lines = self.filtered(
            lambda line: not line.display_type and line.product_id.type == "consu"
        )
        date_groups = order_lines.grouped(
            lambda line: line._purchase_split_date_get_group_keys(picking)
        )
        for key, po_lines in date_groups.items():
            picking_contains_all_lines = (
                picking.move_ids
                and picking.move_ids.purchase_line_id == po_lines
            )
            if (
                not picking.move_ids
                or picking_contains_all_lines
                or picking.filtered_domain(
                    picking._purchase_split_date_assign_domain(key, tz)
                )
            ):
                moves |= super(PurchaseOrderLine, po_lines)._create_stock_moves(picking)
                continue

            moves_to_assign = super(PurchaseOrderLine, po_lines)._create_stock_moves(
                self.env["stock.picking"]
            )
            moves_to_assign = moves_to_assign.with_context(
                purchase_delivery_split_date=True
            )
            moves_to_assign._action_confirm()._action_assign()
            moves |= moves_to_assign
        return moves

    def _compute_price_unit_and_date_planned_and_name(self):
        """Do not move a manually planned receipt date earlier on quantity change."""
        date_planned_by_record = {line.id: line.date_planned for line in self}
        res = super()._compute_price_unit_and_date_planned_and_name()
        for line in self:
            previous_date = date_planned_by_record[line.id]
            if previous_date and line.date_planned <= previous_date:
                line.date_planned = previous_date
        return res
