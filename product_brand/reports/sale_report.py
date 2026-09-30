# Copyright 2018 Tecnativa - David Vidal
# Copyright 2020 Tecnativa - Joao Marques
# Copyright 2022 NuoBiT - Eric Antones
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import fields, models
from odoo.models import TableSQL


class SaleReport(models.Model):
    _inherit = "sale.report"

    product_brand_id = fields.Many2one(comodel_name="product.brand", string="Brand")

    def _select_dict(self, table: TableSQL):
        res = super()._select_dict(table)
        res["product_brand_id"] = table.product_id.product_tmpl_id.product_brand_id
        return res

    def _groupby_list(self, table: TableSQL):
        res = super()._groupby_list(table)
        res.append(table.product_id.product_tmpl_id.product_brand_id)
        return res
