# Copyright 2021 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import pytz

from odoo import models
from odoo.fields import Domain


class StockMove(models.Model):
    _inherit = "stock.move"

    def _purchase_split_date_get_group_keys(self):
        tz = self.picking_type_id.warehouse_id.partner_id.tz
        wh_tz = pytz.timezone(tz) if tz else self.env.tz
        # In Odoo 20 the planned date of an incoming move is stored in ``date``.
        # ``date_deadline`` is the promised/deadline date and must not be used
        # to determine the reception picking day.
        date_planned_tz = self.date.astimezone(pytz.utc).astimezone(wh_tz)
        date = date_planned_tz.date()
        # Split date value to obtain only the attributes year, month and day
        key = (("date_planned", date),)
        return key

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        if self.env.context.get("purchase_delivery_split_date"):
            key = self._purchase_split_date_get_group_keys()
            tz = self.picking_type_id.warehouse_id.partner_id.tz
            domain = Domain.AND(
                [domain, self.picking_id._purchase_split_date_assign_domain(key, tz)]
            )
        return domain

    def write(self, vals):
        res = super().write(vals)
        # purchase_stock in Odoo 20 updates ``date`` when a purchase line's
        # planned date changes (Odoo 19 used ``date_deadline`` for this).
        if "date" in vals and not self.env.context.get(
            "purchase_delivery_split_date_update"
        ):
            self._purchase_split_by_date(vals["date"])
        return res

    def _purchase_split_by_date(self, new_date):
        po_moves = self.filtered(
            lambda m: m.purchase_line_id and m.state not in ("done", "cancel")
        )
        if not po_moves:
            return
        # The date has already been written by the caller in Odoo 20.  Keep
        # this guarded write for callers that invoke the helper directly and
        # prevent it from recursively triggering the split logic.
        po_moves.with_context(
            purchase_delivery_split_date_update=True
        ).write({"date": new_date})
        for picking, moves in po_moves.grouped("picking_id").items():
            if picking.printed:
                # Do not split by date anymore
                continue
            # the picking is not valid anymore
            reserved_moves = moves.filtered(
                lambda m: m.state in ("partially_available", "assigned")
            )
            reserved_moves._do_unreserve()
            moves.picking_id = False
            if picking.move_ids:
                # recompute the picking dates as some moves have been
                # removed
                picking._compute_scheduled_date()
                picking._compute_date_deadline()
            else:
                picking.state = "cancel"
            moves.with_context(purchase_delivery_split_date=True)._assign_picking()
            reserved_moves._action_assign()

    def _get_new_picking_values(self):
        vals = super()._get_new_picking_values()
        if self.env.context.get("purchase_delivery_split_date"):
            is_dropship = all([move._is_dropshipped() for move in self])
            if not vals.get("partner_id") or is_dropship:
                partners = self.purchase_line_id.partner_id
                vals["partner_id"] = next(iter(partners), partners).id
        return vals

    def _assign_picking_values(self, picking):
        vals = super()._assign_picking_values(picking)
        # The core function will remove the partner from the picking if it is
        # different than the one on the moves (Destination Address).
        # For dropshipping the partner on the pick is the contact !
        if self.env.context.get("purchase_delivery_split_date"):
            if "partner_id" in vals.keys():
                vals.pop("partner_id")
        return vals
