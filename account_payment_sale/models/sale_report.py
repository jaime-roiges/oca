# Copyright 2021-2022 Akretion France (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.models import TableSQL


class SaleReport(models.Model):
    _inherit = "sale.report"

    payment_mode_id = fields.Many2one(
        "account.payment.mode",
        string="Payment Mode",
        readonly=True,
    )

    def _select_dict(self, table: TableSQL):
        res = super()._select_dict(table)
        res["payment_mode_id"] = table.order_id.payment_mode_id
        return res
