# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from babel.numbers import format_decimal

from odoo import fields, models
from odoo.http import request

from .packaging import _tl_packaging_summary


def _website_visitor(website):
    """Do not disclose commercial agreements to visitors or another website."""
    try:
        user = request.env.user
        if user._is_public() or not website or website != request.website:
            return False
        return user.partner_id
    except (RuntimeError, AttributeError):
        return False


def _tl_is_contract_offer(currency, usual_price, contractual_price):
    """True only for a customer-visible, currency-significant reduction.

    Both prices must already be expressed in the same currency and in the
    same tax-display regime.  Using the currency precision also prevents
    showing a strikethrough for sub-cent rounding differences.
    """
    return currency.compare_amounts(usual_price, contractual_price) == 1


def _tl_contract_availability_rows(lines, language, selected_uom=None, product=None):
    """Only serialize lines previously restricted to the logged-in customer.

    The balance is the OCA contract balance (draft quotations can contribute to
    its consumption); it must not be labelled as physically available stock.
    Quantities stay in each contract line's UoM, with a separate conversion
    into the product's currently selected website packaging.
    """
    rows = []
    for line in lines:
        row = {
            "id": line.id,
            "contract_name": line.order_id.name,
            "quantity": max(0.0, line.remaining_uom_qty),
            "quantity_display": format_decimal(
                max(0.0, line.remaining_uom_qty),
                format="#,##0.######", locale=language or "en_US",
            ),
            "uom_name": line.product_uom.name,
        }
        if product:
            row.update(_tl_packaging_summary(
                line, product, selected_uom, language,
            ))
        rows.append(row)
    return rows


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tl_contract_whole_pack_only = fields.Boolean(
        string="Whole packages for contractual website sales",
        default=True,
        help=(
            "For contracted eCommerce orders, packaging units (boxes/pallets) "
            "must be purchased in whole numbers. Individual units are unaffected."
        ),
    )

    def _get_sales_prices(self, pricelist_sudo, fiscal_position_sudo, website):
        prices = super()._get_sales_prices(pricelist_sudo, fiscal_position_sudo, website)
        partner = _website_visitor(website)
        if not partner:
            return prices
        for template in self:
            # In a multi-variant card there is no single defensible contract
            # price. The selected variant's page is handled below instead.
            if template.product_variant_count != 1 or not template.product_variant_id:
                continue
            product = template.product_variant_id
            candidates = self.env["sale.blanket.order.line"]._tl_website_candidates(
                product, partner, website.company_id, pricelist_sudo.currency_id
            ).filtered(lambda line: line._tl_available_for_sale_line(1, product._get_main_uom()))
            if len(candidates) != 1:
                continue
            line = candidates[0]
            before_tax = line._tl_price_for_uom(product._get_main_uom())
            product_taxes = product.sudo().taxes_id._filter_taxes_by_company()
            price = template._apply_taxes_to_price(
                before_tax, website.currency_id,
                product_taxes=product_taxes,
                taxes=fiscal_position_sudo.map_tax(product_taxes), website=website,
            )
            if template.id in prices:
                # The original website price comes from the *actual pricelist*
                # applied to this customer, not the public product list price.
                # Both values have already passed through the same fiscal
                # position and tax-display rules.
                normal_price = prices[template.id]["price_reduce"]
                is_hidden = (
                    website.prevent_sale
                    and website.currency_id.is_zero(price)
                    and website._prevent_product_sale(template, True)
                )
                offer = not is_hidden and _tl_is_contract_offer(
                    website.currency_id, normal_price, price
                )
                prices[template.id]["raw_pricelist_price"] = before_tax
                prices[template.id]["price_reduce"] = price
                if offer:
                    # Odoo 20's own shop tile template renders base_price in
                    # <del> and price_reduce as the effective selling price.
                    prices[template.id]["base_price"] = normal_price
                else:
                    # An old pricelist discount/comparison price must not be
                    # advertised as an additional contractual discount.
                    prices[template.id].pop("base_price", None)
                prices[template.id]["tl_contract_price"] = True
                prices[template.id]["tl_contract_offer"] = offer
                if website.show_product_reference_price:
                    price_per_base_uom = product._get_main_uom()._compute_price(
                        price=price, to_unit=product.uom_id
                    )
                    prices[template.id]["base_unit_price"] = product._get_base_unit_price(
                        price_per_base_uom
                    )
        return prices

    def _get_additional_combination_info(
        self, product_or_template, quantity, uom, website, pricelist,
        fiscal_position, **kwargs
    ):
        values = super()._get_additional_combination_info(
            product_or_template, quantity, uom, website, pricelist,
            fiscal_position, **kwargs
        )
        partner = _website_visitor(website)
        if not partner or product_or_template._name != "product.product":
            return values
        # For the product page, show every active contract belonging to the
        # authenticated customer, even if it is exhausted or cannot cover the
        # current quantity. Only a single eligible contract sets the price.
        contract_lines = self.env["sale.blanket.order.line"]._tl_website_candidates(
            product_or_template, partner, website.company_id, pricelist.currency_id
        )
        values["tl_contract_availabilities"] = _tl_contract_availability_rows(
            contract_lines, self.env.lang, selected_uom=uom,
            product=product_or_template,
        )
        eligible_lines = contract_lines.filtered(
            lambda line: line._tl_available_for_sale_line(quantity, uom)
        )
        if len(eligible_lines) != 1:
            return values
        agreement = eligible_lines[0]
        base = agreement._tl_price_for_uom(uom)
        product_taxes = product_or_template.sudo().taxes_id._filter_taxes_by_company()
        visible_price = product_or_template._apply_taxes_to_price(
            base, website.currency_id, product_taxes=product_taxes,
            taxes=fiscal_position.map_tax(product_taxes), website=website,
        )
        # Keep the regular *customer* price returned by Odoo 20, including its
        # tax display, as the reference price.  Contract prices use the same
        # tax and fiscal-position conversion above.
        usual_price = values["price"]
        offer = _tl_is_contract_offer(website.currency_id, usual_price, visible_price)
        is_zero = website.currency_id.is_zero(visible_price)
        prevent_sale = website._prevent_product_sale(product_or_template, is_zero)
        hide_price = prevent_sale and is_zero
        if hide_price:
            offer = False  # Do not leak the reference price in hidden-price mode.
        values.update({
            "price": visible_price,
            "list_price": usual_price if offer else visible_price,
            "raw_pricelist_price": base,
            "has_discounted_price": offer,
            # A product's generic compare-at price cannot be stacked on top
            # of a contractual offer: only one authentic reference price.
            "compare_list_price": 0,
            "tl_contract_price": True,
            "tl_contract_offer": offer,
            "tl_contract_line_id": agreement.id,
            "tl_contract_remaining_qty": agreement.remaining_uom_qty,
            "prevent_sale": prevent_sale,
            "hide_price": hide_price,
        })
        return values
