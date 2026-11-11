from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    tl_demo_generation_run_id = fields.Many2one(
        "tl.demo.generation.run",
        string="Demo generation batch",
        index=True,
        copy=False,
        ondelete="restrict",
        readonly=True,
    )
