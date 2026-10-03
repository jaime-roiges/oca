# Copyright 2019 Tecnativa - David Vidal
# Copyright 2019 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models


class ProductSupplierInfo(models.Model):
    _name = "product.supplierinfo"
    _inherit = ["purchase.triple.discount.mixin", "product.supplierinfo"]

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if not self.partner_id:
            return
        self.update(
            {
                field: self.partner_id[f"default_supplierinfo_{field}"]
                for field in self._get_multiple_discount_field_names()
            }
        )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        partner_id = res.get("partner_id") or self.env.context.get("default_partner_id")
        partner = self.env["res.partner"].browse(partner_id).exists()
        if partner:
            res.update(
                {
                    field: partner[f"default_supplierinfo_{field}"]
                    for field in self._get_multiple_discount_field_names()
                    if field in fields_list
                }
            )
        return res

    @api.model
    def _get_po_to_supplierinfo_synced_fields(self):
        """Compatibility hook for addons that still synchronize PO/vendor fields.

        This hook existed in Odoo 19 core but is no longer provided by Odoo 20.
        Keep it as an extension point without requiring a missing super method.
        """
        parent = getattr(super(), "_get_po_to_supplierinfo_synced_fields", None)
        res = list(parent()) if parent else []
        for field in self._get_multiple_discount_field_names():
            if field not in res:
                res.append(field)
        return res
