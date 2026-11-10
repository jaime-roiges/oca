# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    tl_blanket_line_id = fields.Many2one(
        "sale.blanket.order.line", string="Reserved for blanket line",
        ondelete="restrict", copy=False, index=True, readonly=True,
    )
