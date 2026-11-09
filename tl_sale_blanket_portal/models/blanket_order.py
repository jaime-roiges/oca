# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Distinguish explicitly cancelled contracts from naturally expired ones.

The upstream sale_blanket_order implementation maps its action_cancel to the
'expired' state. A separate flag retains the business distinction without
altering any OCA selection values or existing external IDs.
"""
from odoo import api, fields, models


class SaleBlanketOrder(models.Model):
    _inherit = "sale.blanket.order"

    tl_portal_cancelled = fields.Boolean(
        string="Cancelled contract",
        default=False,
        copy=False,
        index=True,
        readonly=True,
        help="Set when the contract is explicitly cancelled, rather than expired by date.",
    )

    @api.depends(
        "line_ids.remaining_uom_qty",
        "validity_date",
        "confirmed",
        "tl_portal_cancelled",
    )
    def _compute_state(self):
        # In OCA, 'state' is a stored compute. Guarantee that a cancelled
        # agreement cannot silently become open again after a recomputation.
        super()._compute_state()
        for order in self.filtered("tl_portal_cancelled"):
            order.state = "expired"

    def action_cancel(self):
        # Preserve OCA's restriction on cancelling agreements with active SOs.
        result = super().action_cancel()
        self.write({"tl_portal_cancelled": True})
        return result

    def set_to_draft(self):
        result = super().set_to_draft()
        self.write({"tl_portal_cancelled": False})
        return result

    def action_confirm(self):
        # Explicit reconfirmation removes the cancelled marker. In the event
        # of an unsuccessful confirmation the transaction is rolled back.
        self.write({"tl_portal_cancelled": False})
        return super().action_confirm()
