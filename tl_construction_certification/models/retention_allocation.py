from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionRetentionAllocation(models.Model):
    _name = "construction.retention.allocation"
    _description = "Construction retention release allocation"
    _check_company_auto = True
    _source_unique = models.Constraint(
        "UNIQUE(certification_id, source_line_id)",
        "A retention can only be selected once per liquidation.",
    )

    certification_id = fields.Many2one("construction.certification", required=True, ondelete="cascade", index=True, check_company=True)
    company_id = fields.Many2one(related="certification_id.company_id", store=True)
    currency_id = fields.Many2one(related="certification_id.currency_id", store=True)
    source_line_id = fields.Many2one("account.move.line", required=True, ondelete="restrict", index=True, check_company=True)
    maturity_date = fields.Date(related="source_line_id.date_maturity", readonly=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")

    @api.constrains("amount")
    def _check_positive_amount(self):
        for allocation in self:
            if allocation.currency_id.compare_amounts(allocation.amount, 0) <= 0:
                raise ValidationError(_("The retention allocation amount must be positive."))

    @api.model_create_multi
    def create(self, vals_list):
        certs = self.env["construction.certification"].browse([v.get("certification_id") for v in vals_list if v.get("certification_id")]).exists()
        if any(cert.state not in cert._open_states for cert in certs):
            raise UserError(_("Retention allocations can only be changed on an open certification."))
        return super().create(vals_list)

    def write(self, vals):
        if any(line.certification_id.state not in line.certification_id._open_states for line in self):
            raise UserError(_("Retention allocations can only be changed on an open certification."))
        if vals.get("certification_id"):
            cert = self.env["construction.certification"].browse(vals["certification_id"])
            if cert.state not in cert._open_states:
                raise UserError(_("Retention allocations can only be changed on an open certification."))
        return super().write(vals)

    def unlink(self):
        if any(line.certification_id.state not in line.certification_id._open_states for line in self):
            raise UserError(_("Retention allocations can only be changed on an open certification."))
        return super().unlink()
