# Copyright 2019 Simone Rubino - Agile Business Group
# Copyright 2023 Simone Rubino - Aion Tech
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import operator
from functools import reduce

from odoo import api, fields, models
from odoo.tools import float_round, format_amount, get_lang


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    discount2 = fields.Float(
        string="Discount 2 (%)",
        help="Second discount applied on a sale order line.",
        digits="Discount",
    )
    discount3 = fields.Float(
        string="Discount 3 (%)",
        help="Third discount applied on a sale order line.",
        digits="Discount",
    )

    def _get_triple_discounts_perc(self):
        """Return the three sequential percentages used by this pricelist rule.

        In Odoo 20 the first discount is always stored in ``price_discount``.
        ``price_markup`` is only an inverse presentation of a negative
        ``price_discount`` for surcharge rules.
        """
        self.ensure_one()
        return [self.price_discount or 0.0, self.discount2 or 0.0, self.discount3 or 0.0]

    def _get_triple_discount(self):
        """Return the equivalent single percentage for all sequential discounts."""
        self.ensure_one()
        factors = [1.0 - discount / 100.0 for discount in self._get_triple_discounts_perc()]
        return 100.0 - reduce(operator.mul, factors, 1.0) * 100.0

    def _has_extra_discounts(self):
        self.ensure_one()
        return bool(self.discount2 or self.discount3)

    def _compute_price(self, product, quantity, uom, **kwargs):
        """Apply discount2/discount3 without mutating the persisted pricelist rule.

        The 19.0 migration proposal temporarily wrote the aggregate discount into
        the rule. Odoo 20 can reuse the core pricing algorithm safely by applying
        the equivalent percentage locally and leaving the record untouched.
        """
        if (
            not self
            or self.compute_price not in ("discount", "markup")
            or not self._has_extra_discounts()
        ):
            return super()._compute_price(product, quantity, uom, **kwargs)

        self.ensure_one()
        product.ensure_one()
        uom = uom or product._get_main_uom()
        uom.ensure_one()

        base_price = self._compute_base_price(product, quantity, uom, **kwargs)
        effective_discount = self._get_triple_discount()
        price = base_price - (base_price * effective_discount / 100.0)
        product_uom = product.uom_id

        if self.price_round:
            price = float_round(price, precision_rounding=self.price_round)
        if self.price_surcharge:
            price += product_uom._compute_price(self.price_surcharge, uom)
        if self.price_min_margin:
            price = max(
                price,
                base_price + product_uom._compute_price(self.price_min_margin, uom),
            )
        if self.price_max_margin:
            price = min(
                price,
                base_price + product_uom._compute_price(self.price_max_margin, uom),
            )
        return price

    @api.depends(
        "compute_price",
        "fixed_price",
        "pricelist_id",
        "price_discount",
        "price_markup",
        "price_surcharge",
        "base",
        "base_pricelist_id",
        "discount2",
        "discount3",
    )
    def _compute_price_label(self):
        super()._compute_price_label()
        for item in self.filtered(
            lambda rule: rule.compute_price != "fixed" and rule._has_extra_discounts()
        ):
            base_str = item._get_price_label_base_str()
            extra_fee_str = ""
            if item.price_surcharge > 0:
                extra_fee_str = item.env._(
                    "+ %(amount)s extra fee",
                    amount=format_amount(
                        item.env, abs(item.price_surcharge), currency=item.currency_id
                    ),
                )
            elif item.price_surcharge < 0:
                extra_fee_str = item.env._(
                    "- %(amount)s rebate",
                    amount=format_amount(
                        item.env, abs(item.price_surcharge), currency=item.currency_id
                    ),
                )

            effective_discount = item._get_triple_discount()
            if effective_discount < 0:
                discount_type = item.env._("surcharge")
                percentage = item._get_integer(abs(effective_discount))
            else:
                discount_type = item.env._("discount")
                percentage = item._get_integer(effective_discount)

            item.price = item.env._(
                "%(percentage)s %% %(discount_type)s on %(base)s %(extra)s",
                percentage=percentage,
                discount_type=discount_type,
                base=base_str,
                extra=extra_fee_str,
            )

    @api.depends_context("lang")
    @api.depends(
        "base",
        "compute_price",
        "price_discount",
        "price_round",
        "price_surcharge",
        "discount2",
        "discount3",
    )
    def _compute_rule_tip(self):
        super()._compute_rule_tip()
        lang = self.env["res.lang"].browse(get_lang(self.env).id)
        for item in self.filtered(
            lambda rule: rule.compute_price != "fixed"
            and rule.base
            and rule._has_extra_discounts()
        ):
            base_amount = 100.0
            discount_factor = (100.0 - item._get_triple_discount()) / 100.0
            discounted_price = base_amount * discount_factor
            if item.price_round:
                discounted_price = float_round(
                    discounted_price, precision_rounding=item.price_round
                )
            amount = format_amount(item.env, base_amount, item.currency_id)
            factor = lang.format("%g", discount_factor, grouping=True)
            surcharge = format_amount(item.env, item.price_surcharge, item.currency_id)
            total = format_amount(
                item.env, discounted_price + item.price_surcharge, item.currency_id
            )
            item.rule_tip = f"{amount} × {factor} + {surcharge} = {total}"

    @api.depends(
        "compute_price",
        "price_discount",
        "price_round",
        "price_surcharge",
        "price_min_margin",
        "price_max_margin",
        "discount2",
        "discount3",
    )
    def _compute_is_plain_discount(self):
        super()._compute_is_plain_discount()
        for item in self.filtered(lambda rule: rule._has_extra_discounts()):
            item.is_plain_discount = item.compute_price == "discount" and (
                item._get_triple_discount() > 0
                and not item.price_round
                and not item.price_surcharge
                and not item.price_min_margin
                and not item.price_max_margin
            )
