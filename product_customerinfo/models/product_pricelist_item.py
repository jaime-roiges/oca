# Copyright 2015 OdooMRP team
# Copyright 2015 AvanzOSC
# Copyright 2015 Tecnativa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    base = fields.Selection(
        selection_add=[("partner", "Partner Prices on the product form")],
        ondelete={"partner": "set default"},
    )

    def _compute_price(self, product, quantity, uom, **kwargs):
        """Apply the discount stored on customerinfo before pricelist adjustments."""
        return super()._compute_price(
            product.with_context(include_customerinfo_discount=True),
            quantity,
            uom,
            **kwargs,
        )

    def _compute_base_price(
        self,
        product,
        quantity,
        uom,
        *,
        currency=None,
        date=False,
        depth=0,
        base_prices=None,
        **kwargs,
    ):
        """Handle the custom ``partner`` pricelist base explicitly on Odoo 20.

        Odoo 19 delegated unknown pricelist bases to ``product._price_compute``.
        Odoo 20 treats every non-pricelist/non-cost base as ``list_price``, so the
        custom customer price must now be handled here.
        """
        if self.base == "partner":
            currency = currency or self.currency_id or self.env.company.currency_id
            currency.ensure_one()
            return product._price_compute(
                "partner",
                uom=uom,
                currency=currency,
                company=self.env.company,
                date=date,
            )[product.id]
        return super()._compute_base_price(
            product,
            quantity,
            uom,
            currency=currency,
            date=date,
            depth=depth,
            base_prices=base_prices,
            **kwargs,
        )

    def _show_discount(self):
        # Show discount when pricelist item is based on customerinfo price.
        res = super()._show_discount()
        if (
            self
            and self._is_discount_feature_enabled()
            and self.compute_price == "discount"
            and self.base == "partner"
        ):
            return True
        return res
