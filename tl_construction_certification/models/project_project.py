# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    certification_count = fields.Integer(
        compute="_compute_certification_count",
    )

    def _compute_certification_count(self):
        for project in self:
            project.certification_count = self.env["construction.certification"].search_count(
                [("project_id", "=", project.id)]
            )

    def action_view_certifications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Work Certifications",
            "res_model": "construction.certification",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
        }
