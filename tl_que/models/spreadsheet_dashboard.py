import json

from odoo import api, models
from odoo.tools.misc import file_open

_DASHBOARDS = (
    (
        "construction_developer.spreadsheet_dashboard_cost_nature",
        "tl_que/static/src/binary/spreadsheet_dashboard/CostNature.osheet.json",
        "Naturaleza de coste",
    ),
    (
        "construction_developer.spreadsheet_dashboard_progress_report",
        "tl_que/static/src/binary/spreadsheet_dashboard/Progress.osheet.json",
        "Informe de avance",
    ),
)


class SpreadsheetDashboard(models.Model):
    _inherit = "spreadsheet.dashboard"

    @api.model
    def _tl_que_reload_cost_nature(self):
        for xmlid, path, name in _DASHBOARDS:
            dashboard = self.env.ref(xmlid, raise_if_not_found=False)
            if not dashboard:
                continue
            with file_open(path, "rb") as handle:
                payload = json.loads(handle.read().decode())
            dashboard.spreadsheet_data = json.dumps(payload)
            dashboard.name = name
            Revision = self.env.get("spreadsheet.revision")
            if Revision is not None and "res_id" in Revision._fields:
                domain = [("res_id", "=", dashboard.id)]
                if "res_model" in Revision._fields:
                    domain.append(("res_model", "=", "spreadsheet.dashboard"))
                Revision.sudo().search(domain).unlink()
