from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    tl_demo_generation_run_id = fields.Many2one(
        "tl.demo.generation.run",
        string="Demo generation batch",
        index=True,
        copy=False,
        ondelete="restrict",
        readonly=True,
    )
    tl_demo_product_id = fields.Many2one(
        "product.product",
        string="Demo product",
        index=True,
        copy=False,
        readonly=True,
    )
