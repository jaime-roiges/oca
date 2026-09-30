# Copyright 2018 Tecnativa - David Vidal
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import fields, models
from odoo.models import TableSQL
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

    product_brand_id = fields.Many2one(comodel_name="product.brand", string="Brand")

    def _select_list(self, table: TableSQL):
        res = super()._select_list(table)
        res.append(
            SQL(
                "%s AS product_brand_id",
                table.product_id.product_tmpl_id.product_brand_id,
            )
        )
        return res
