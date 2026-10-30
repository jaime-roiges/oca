# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""BC3 source namespaces and permanent audit snapshots.

A concept code is only unique inside one BC3 source/catalog: the same code can
represent unrelated materials across budgets, publishers and companies.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Bc3Catalog(models.Model):
    _name = "bc3.catalog"
    _description = "BC3 Price Catalog / Source"
    _order = "name, id"
    _check_company_auto = True

    _source_company_uniq = models.Constraint(
        "UNIQUE(company_id, name)",
        "A BC3 catalog with this name already exists in this company.",
    )

    name = fields.Char(required=True, index=True)
    edition = fields.Char(
        string="Source Edition", index=True,
        help="Optional human-approved edition of the source price base. "
        "A code may be reused in different editions with different prices."
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
        index=True, ondelete="restrict",
    )
    description = fields.Text()
    product_ids = fields.One2many("product.template", "bc3_catalog_id")
    import_ids = fields.One2many("bc3.import.history", "catalog_id")


class Bc3ImportHistory(models.Model):
    _name = "bc3.import.history"
    _description = "BC3 Import Audit Trail"
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)
    file_data = fields.Binary(
        string="Original BC3", attachment=True, required=True, readonly=True,
        help="Original bytes as received; never rewritten by subsequent imports.",
    )
    checksum_sha256 = fields.Char(readonly=True, required=True, index=True)
    file_size = fields.Integer(readonly=True)
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, index=True, ondelete="restrict",
    )
    catalog_id = fields.Many2one(
        "bc3.catalog", required=True, readonly=True,
        ondelete="restrict", check_company=True,
    )
    sale_order_id = fields.Many2one(
        "sale.order", readonly=True, ondelete="restrict", check_company=True,
    )
    user_id = fields.Many2one("res.users", readonly=True, required=True)
    info_type = fields.Char(readonly=True)
    import_mode = fields.Char(readonly=True)
    validation_mode = fields.Char(readonly=True)
    price_scope = fields.Integer(readonly=True)
    warnings = fields.Text(readonly=True)
    summary = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        # A hash is verified on every archive creation, even via RPC.
        import base64
        import hashlib
        import binascii
        for vals in vals_list:
            encoded = vals.get("file_data")
            if not encoded:
                raise UserError(_("Original BC3 bytes must be archived."))
            try:
                original = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError, binascii.Error) as error:
                raise UserError(_("Invalid BC3 archive payload.")) from error
            digest = hashlib.sha256(original).hexdigest()
            if vals.get("checksum_sha256") != digest:
                raise UserError(_("BC3 archive digest does not match the file."))
        return super().create(vals_list)

    def write(self, vals):
        raise UserError(_("BC3 import history is immutable. Create a new import instead."))

    def unlink(self):
        raise UserError(_("BC3 import history cannot be deleted through the user interface."))
