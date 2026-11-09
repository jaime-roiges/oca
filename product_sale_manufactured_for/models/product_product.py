from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    manufactured_for_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="product_product_manuf_for_partner_rel",
        column1="product_id",
        column2="partner_id",
        string="Manufactured for",
        help="When empty the product is available to every customer. "
        "When set, website sales are limited to these contacts and their companies.",
    )
