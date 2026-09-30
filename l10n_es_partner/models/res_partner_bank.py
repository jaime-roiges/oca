# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3).

from odoo import fields, models


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    bank_long_name = fields.Char(string="Bank Long Name", size=128)
    bank_vat = fields.Char(string="Bank VAT", size=32, help="Bank VAT number")
    bank_website = fields.Char(string="Bank Website", size=256)
