from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    construction_advance_account_id = fields.Many2one(
        related="company_id.construction_advance_account_id", readonly=False,
    )
    construction_retention_account_id = fields.Many2one(
        related="company_id.construction_retention_account_id", readonly=False,
    )
