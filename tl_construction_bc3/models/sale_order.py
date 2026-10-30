# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    bc3_catalog_id = fields.Many2one(
        "bc3.catalog", string="BC3 Source Catalog", copy=False,
        ondelete="restrict", check_company=True,
    )
    bc3_import_ids = fields.One2many(
        "bc3.import.history", "sale_order_id", string="BC3 Import History",
        readonly=True,
    )
    bc3_filename = fields.Char(string="BC3 File", copy=False)
    bc3_info_type = fields.Selection(
        selection=[
            ("1", "Database"),
            ("2", "Budget"),
            ("3", "Certification"),
            ("4", "Database update"),
        ],
        string="BC3 Information",
        copy=False,
    )
    bc3_ci = fields.Float(string="Indirect Costs %", digits=(16, 4), copy=False)
    bc3_gg = fields.Float(string="Overheads %", digits=(16, 4), copy=False)
    bc3_bi = fields.Float(string="Industrial Profit %", digits=(16, 4), copy=False)
    bc3_baja = fields.Float(string="Award Discount %", digits=(16, 4), copy=False)
    bc3_iva = fields.Float(string="VAT %", digits=(16, 4), copy=False)
    bc3_currency = fields.Char(string="BC3 Currency", copy=False)
    bc3_comment = fields.Text(string="BC3 Comment", copy=False)
    bc3_import_summary = fields.Text(
        string="BC3 Import Summary", copy=False,
        help="Updated on each BC3 import, without changing standard sale terms.",
    )
