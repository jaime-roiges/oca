from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    tl_demo_generation_run_id = fields.Many2one(
        "tl.demo.generation.run",
        string="Demo generation batch",
        index=True,
        copy=False,
        ondelete="restrict",
        readonly=True,
    )
