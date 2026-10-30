# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    bc3_catalog_id = fields.Many2one(
        "bc3.catalog", string="BC3 Source Catalog", index=True,
        copy=False, ondelete="restrict", check_company=True,
        help="Allows the same concept code to exist in different price catalogs.",
    )
    bc3_code = fields.Char(
        string="BC3 Code",
        index=True,
        copy=False,
        help="Concept code from a FIEBDC-3 file, without the chapter marks # and ##.",
    )
    bc3_concept_type = fields.Char(
        string="BC3 Concept Type",
        help="FIEBDC concept type: 0 unclassified, 1 labor, 2 machinery, "
        "3 material, 4 waste component, 5 waste classification. "
        "Other codes from the price-revision annexes are kept as-is.",
    )
    bc3_unit = fields.Char(
        string="BC3 Unit",
        help="Unit of measure as written in the BC3 file.",
    )
    bc3_text = fields.Text(string="BC3 Description")
