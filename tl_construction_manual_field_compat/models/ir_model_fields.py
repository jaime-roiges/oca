# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    @api.model
    def _instanciate_attrs(self, field_data):
        attrs = super()._instanciate_attrs(field_data)
        if attrs is not None:
            return attrs
        if not (
            not self.pool.loaded
            and field_data.get("state") == "manual"
            and field_data.get("model") == "sale.order"
            and field_data.get("name") == "x_total_discount_amount"
            and field_data.get("ttype") == "monetary"
            and field_data.get("currency_field") == "currency_id"
        ):
            return attrs
        # Reuse core's full attribute and compute handling, without changing
        # the actual metadata or the currency field in the returned attrs.
        temporary_data = dict(field_data, currency_field=False)
        attrs = super()._instanciate_attrs(temporary_data)
        if attrs is not None:
            attrs["currency_field"] = field_data["currency_field"]
        return attrs
