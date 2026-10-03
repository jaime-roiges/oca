# Copyright 2017-19 Tecnativa - David Vidal
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import Command, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_supplier_info(self, partner, line, price, currency):
        """Odoo 20 removed this former purchase hook.

        Keep the Odoo 19 semantics locally because purchase_triple_discount
        promises to create the missing vendor pricelist on PO confirmation and
        to copy its three discount values.
        """
        supplierinfo = {
            "partner_id": partner.id,
            "sequence": (
                max(line.product_id.seller_ids.mapped("sequence")) + 1
                if line.product_id.seller_ids
                else 1
            ),
            "min_qty": 1.0,
            "price": price,
            "currency_id": currency.id,
            "delay": 0,
            **{
                fname: line[fname]
                for fname in line._get_multiple_discount_field_names()
            },
        }
        return supplierinfo

    def _add_supplier_to_product(self):
        """Reintroduce the Odoo 19 behavior removed from Odoo 20 core."""
        for order in self:
            for line in order.order_line.filtered(
                lambda purchase_line: purchase_line.product_id
                and not purchase_line.display_type
            ):
                partner = order.partner_id.commercial_partner_id
                already_seller = (partner | order.partner_id) & line.product_id.seller_ids.mapped(
                    "partner_id"
                )
                if already_seller or len(line.product_id.seller_ids) > 10:
                    continue

                price = line.price_unit
                default_uom = line.product_id.product_tmpl_id.uom_id
                if default_uom != line.uom_id:
                    price = line.uom_id._compute_price(price, default_uom)

                supplierinfo = order._prepare_supplier_info(
                    partner, line, price, line.currency_id
                )
                if line.selected_seller_id:
                    supplierinfo.update(
                        {
                            "product_name": line.selected_seller_id.product_name,
                            "product_code": line.selected_seller_id.product_code,
                            "uom_id": line.uom_id.id,
                        }
                    )
                line.product_id.product_tmpl_id.sudo().write(
                    {"seller_ids": [Command.create(supplierinfo)]}
                )

    def button_confirm(self):
        orders_to_process = self.filtered(lambda order: order.state in ("draft", "sent"))
        res = super().button_confirm()
        orders_to_process._add_supplier_to_product()
        return res
