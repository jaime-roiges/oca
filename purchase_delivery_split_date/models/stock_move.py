# Copyright 2021 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import pytz

from odoo import models
from odoo.fields import Domain


class StockMove(models.Model):
    _inherit = "stock.move"

    def _purchase_split_date_get_group_keys(self):
        self.ensure_one()
        tz = self.picking_type_id.warehouse_id.partner_id.tz
        wh_tz = pytz.timezone(tz) if tz else self.env.tz
        date_tz = self.date.astimezone(pytz.utc).astimezone(wh_tz)
        return (("date_planned", date_tz.date()),)

    def _key_assign_picking(self):
        """Include the receipt date in Odoo 20's initial picking grouping key."""
        key = super()._key_assign_picking()
        if self.env.context.get("purchase_delivery_split_date") and self.purchase_line_id:
            key += (self._purchase_split_date_get_group_keys(),)
        return key

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        if self.env.context.get("purchase_delivery_split_date") and self.purchase_line_id:
            key = self._purchase_split_date_get_group_keys()
            tz = self.picking_type_id.warehouse_id.partner_id.tz
            domain = Domain.AND(
                [domain, self.picking_id._purchase_split_date_assign_domain(key, tz)]
            )
        return domain

    def write(self, vals):
        res = super().write(vals)
        # In Odoo 20 purchase_stock updates move.date when date_planned changes on
        # an incoming purchase move. date_deadline is reserved for date_promised.
        if "date" in vals:
            self._purchase_split_by_date(vals["date"])
        return res

    def _purchase_split_by_date(self, new_date):
        po_moves = self.filtered(
            lambda move: move.purchase_line_id and move.state not in ("done", "cancel")
        )
        if not po_moves:
            return

        # ``new_date`` has already been written by ``super().write``. Do not write it
        # again here or this method would recurse through ``write``.
        for picking, moves in po_moves.grouped("picking_id").items():
            if not picking or picking.printed:
                continue
            reserved_moves = moves.filtered(
                lambda move: move.state in ("partially_available", "assigned")
            )
            reserved_moves._do_unreserve()
            moves.picking_id = False
            if picking.move_ids:
                picking._compute_scheduled_date()
                picking._compute_date_deadline()
            else:
                picking.state = "cancel"
            moves.with_context(purchase_delivery_split_date=True)._assign_picking()
            reserved_moves._action_assign()

    def _get_new_picking_values(self):
        vals = super()._get_new_picking_values()
        if self.env.context.get("purchase_delivery_split_date"):
            is_dropship = all(move._is_dropshipped() for move in self)
            if not vals.get("partner_id") or is_dropship:
                partners = self.purchase_line_id.partner_id
                vals["partner_id"] = next(iter(partners), partners).id
        return vals

    def _assign_picking_values(self, picking):
        vals = super()._assign_picking_values(picking)
        # Core may remove the partner when move destination addresses differ. Keep
        # the purchase/drop-shipping partner in the split-date flow.
        if self.env.context.get("purchase_delivery_split_date"):
            vals.pop("partner_id", None)
        return vals
