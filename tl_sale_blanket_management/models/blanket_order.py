# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models


class SaleBlanketOrder(models.Model):
    _inherit = "sale.blanket.order"

    tl_portal_visible = fields.Boolean(
        string="Visible in customer portal", default=True,
        help="Only signed-in customers belonging to the commercial company can view it.",
    )
    tl_purchase_ids = fields.One2many(
        "purchase.order", "tl_blanket_order_id", string="Related purchases",
    )
    tl_purchase_count = fields.Integer(compute="_compute_tl_purchase_count")

    @api.depends("tl_purchase_ids")
    def _compute_tl_purchase_count(self):
        for blanket in self:
            blanket.tl_purchase_count = len(blanket.tl_purchase_ids)

    def action_tl_view_purchases(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Related purchases"),
            "res_model": "purchase.order", "view_mode": "list,form",
            "domain": [("tl_blanket_order_id", "=", self.id)],
            "context": {"default_tl_blanket_order_id": self.id},
        }
