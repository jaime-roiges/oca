# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def write(self, vals):
        result = super().write(vals)
        if {"product_id", "order_id", "product_uom_qty"}.intersection(vals):
            self.mapped("order_id").filtered(
                lambda order: order.state in ("sale", "done")
            )._tl_validate_manufactured_products()
        return result
