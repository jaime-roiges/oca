from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if self.env.context.get("construction_keep_links") and "date_maturity" not in (default or {}):
            for line, vals in zip(self, vals_list):
                if line.construction_adjustment_type == "retention" and line.date_maturity:
                    vals["date_maturity"] = line.date_maturity
        return vals_list
