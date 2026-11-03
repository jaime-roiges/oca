import json

from odoo import api, models
from odoo.tools.misc import file_open


class SpreadsheetDashboard(models.Model):
    _inherit = "spreadsheet.dashboard"

    @api.model
    def _tl_que_reload_cost_nature(self):
        dashboard = self.env.ref(
            "construction_developer.spreadsheet_dashboard_cost_nature",
            raise_if_not_found=False,
        )
        if not dashboard:
            return
        with file_open(
            "tl_que/static/src/binary/spreadsheet_dashboard/CostNature.osheet.json",
            "rb",
        ) as handle:
            payload = json.loads(handle.read().decode())
        payload["revisionId"] = "tl-que-1.0.2"
        dashboard.spreadsheet_data = json.dumps(payload)
        Revision = self.env.get("spreadsheet.revision")
        if Revision is not None and "res_id" in Revision._fields:
            domain = [("res_id", "=", dashboard.id)]
            if "res_model" in Revision._fields:
                domain.append(("res_model", "=", "spreadsheet.dashboard"))
            Revision.sudo().search(domain).unlink()
