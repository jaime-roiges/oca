# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.models import TableSQL
from odoo.tools import SQL


class PurchaseReport(models.Model):
    _inherit = "purchase.report"

    product_brand_id = fields.Many2one(comodel_name="product.brand", string="Brand")

    def _select_list(self, table: TableSQL):
        res = super()._select_list(table)
        return [
            *res,
            SQL(
                "%s AS product_brand_id",
                table.product_id.product_tmpl_id.product_brand_id,
            ),
        ]

    def _groupby_list(self, table: TableSQL):
        res = super()._groupby_list(table)
        return [*res, table.product_id.product_tmpl_id.product_brand_id]
