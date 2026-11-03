from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    construction_retention_due_date = fields.Date(
        string="Guarantee Maturity Date",
        copy=False,
        tracking=True,
        help="Default guarantee maturity for new work certifications. Existing certifications keep their own date.",
    )
