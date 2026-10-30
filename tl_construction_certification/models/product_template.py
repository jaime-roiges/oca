# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        res = super().write(vals)
        if "taxes_id" in vals:
            self._refresh_open_construction_invoice_taxes()
        return res

    def _refresh_open_construction_invoice_taxes(self):
        """Recompute only open construction invoice lines.

        ``account.move.line._compute_tax_ids`` must not depend on
        ``product_id.taxes_id``: that dependency recomputes every customer
        invoice. The product change is applied here, and only to draft
        certification lines.
        """
        products = self.product_variant_ids
        if not products:
            return
        lines = self.env["account.move.line"].search([
            ("product_id", "in", products.ids),
            ("move_id.state", "=", "draft"),
            ("construction_certification_line_id", "!=", False),
        ])
        if not lines:
            return
        lines._compute_tax_ids()
        lines._compute_price_unit()
