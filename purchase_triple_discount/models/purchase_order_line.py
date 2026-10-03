# Copyright 2017-19 Tecnativa - David Vidal
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["purchase.triple.discount.mixin", "purchase.order.line"]

    @api.depends("product_qty", "uom_id", "company_id", "order_id.partner_id")
    def _compute_price_unit_and_date_planned_and_name(self):
        res = super()._compute_price_unit_and_date_planned_and_name()
        self._compute_discounts()
        return res

    def _compute_discounts(self):
        for line in self:
            if not line.company_id or not line.product_id or line.invoice_lines:
                continue
            seller = line._get_seller_info()
            if not seller:
                continue
            line.update(
                {
                    fname: seller[fname] or 0.0
                    for fname in line._get_multiple_discount_field_names()
                }
            )

    def _prepare_account_move_line(self, move=False):
        self.ensure_one()
        res = super()._prepare_account_move_line(move)
        res.update(
            {
                fname: self[fname]
                for fname in self._get_multiple_discount_field_names()
            }
        )
        return res

    @api.model
    def _prepare_purchase_order_line(
        self, product_id, product_qty, product_uom, company_id, partner_id, po
    ):
        res = super()._prepare_purchase_order_line(
            product_id, product_qty, product_uom, company_id, partner_id, po
        )

        values = self.env.context.get("procurement_values", {})
        uom_po_qty = product_uom._compute_quantity(
            product_qty, product_id.uom_id, rounding_method="HALF-UP"
        )
        actual_partner = (
            partner_id.partner_id
            if getattr(partner_id, "_name", None) == "product.supplierinfo"
            else partner_id
        )
        today = fields.Date.context_today(self)
        seller = product_id.with_company(company_id)._select_seller(
            partner_id=actual_partner,
            quantity=product_qty if values.get("force_uom") else uom_po_qty,
            date=max(fields.Date.context_today(self, timestamp=po.date_order), today),
            uom_id=product_uom if values.get("force_uom") else product_id.uom_id,
            params={"force_uom": values.get("force_uom")},
        )
        res.update(
            {
                fname: (seller[fname] or 0.0) if seller else 0.0
                for fname in self._get_multiple_discount_field_names()
            }
        )
        return res
