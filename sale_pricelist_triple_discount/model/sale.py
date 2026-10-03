# Copyright 2019 Simone Rubino - Agile Business Group
# Copyright 2023 Simone Rubino - Aion Tech
# Copyright 2025 Ethan Hildick
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends(
        "discount",
        "pricelist_item_id",
        "pricelist_item_id.compute_price",
        "pricelist_item_id.price_discount",
        "pricelist_item_id.discount2",
        "pricelist_item_id.discount3",
        "pricelist_item_id.is_plain_discount",
    )
    def _compute_discounts(self):
        """Expose the original three rule discounts when Odoo shows a line discount.

        For complex pricing rules Odoo 20 bakes the price change into ``price_unit``.
        In that case the line discounts must remain zero to avoid applying them twice.
        """
        res = super()._compute_discounts()
        for line in self:
            if line.combo_item_id:
                linked_line = line._get_linked_line()
                if linked_line:
                    line.discount1 = linked_line.discount1
                    line.discount2 = linked_line.discount2
                    line.discount3 = linked_line.discount3
                    line.discounting_type = linked_line.discounting_type
                continue

            rule = line.pricelist_item_id
            if not rule or rule.compute_price != "discount" or not rule._show_discount():
                continue

            line.discount1 = rule.price_discount
            line.discount2 = rule.discount2
            line.discount3 = rule.discount3
            line.discounting_type = "multiplicative"
        return res
