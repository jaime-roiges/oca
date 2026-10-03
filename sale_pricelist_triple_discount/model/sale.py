# Copyright 2019 Simone Rubino - Agile Business Group
# Copyright 2023 Simone Rubino - Aion Tech
# Copyright 2025 Ethan Hildick
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _recompute_prices(self):
        """Reapply the three visible discounts after Odoo recomputes prices.

        Odoo 20 deliberately invalidates the non-stored ``pricelist_item_id`` and
        recomputes price/discount explicitly when the pricelist changes.  Keep the
        same flow and only synchronize discount1/2/3 afterwards.
        """
        res = super()._recompute_prices()
        self._get_update_prices_lines()._compute_discounts()
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.depends(
        "discount",
        "product_id",
        "product_uom_id",
        "product_uom_qty",
    )
    def _compute_discounts(self):
        """Expose a plain pricelist rule as the original three discounts.

        ``pricelist_item_id`` is a non-stored technical field in Odoo 20.  It must
        not be used as a dependency path for these stored fields: doing so makes
        the ORM build an inverse SQL search on a field with no SQL column when a
        pricelist item is edited.  Depend on the same stored inputs used by the
        core pricelist-item computation and read ``pricelist_item_id`` only at
        compute time.

        For complex pricing rules Odoo 20 bakes the price change into
        ``price_unit``.  In that case the line discounts stay zero to avoid
        applying the rule twice.
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
