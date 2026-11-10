# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Secure contract-aware implementation of the OCA regular-products route.

The upstream OCA module has no data-selection override hook. This addon
therefore overrides its route, but leaves the OCA addon files unchanged.
"""

from odoo import http
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import lazy

from odoo.addons.website_sale.controllers.main import TableCompute
from odoo.addons.website_sale_menu_partner_top_selling.controllers.main import (
    WebsiteSale as OcaRegularProducts,
)

from .ranking import rank_visible_template_ids


class WebsiteSaleRegularContract(OcaRegularProducts):
    """Rank actual sales and apply the active website's partner visibility."""

    @staticmethod
    def _tl_normalized_sales_by_product(website, partner):
        """Read only this commercial customer's confirmed sales, in website company.

        Group per product and UoM rather than summing incomparable box/unit
        quantities. Sales without contracts also belong in repeat purchases;
        an unconfirmed contract by itself is not a sale.
        """
        grouped = (
            request.env["sale.order.line"]
            .sudo()
            ._read_group(
                domain=[
                    (
                        "order_id.partner_id.commercial_partner_id",
                        "=",
                        partner.commercial_partner_id.id,
                    ),
                    ("order_id.company_id", "=", website.company_id.id),
                    ("order_id.state", "in", ["sale", "done"]),
                    ("display_type", "=", False),
                    ("product_id", "!=", False),
                ],
                groupby=["product_id", "product_uom_id"],
                aggregates=["product_uom_qty:sum"],
            )
        )
        quantities = {}
        products_by_template = {}
        for product, sale_uom, quantity in grouped:
            if not product or not sale_uom or quantity <= 0:
                continue
            # A historically purchased variant can no longer be permitted.
            # Never show it just because sale.order.line was read in sudo.
            if not product._website_manufactured_accessible(partner):
                continue
            product = product.with_company(website.company_id)
            main_uom = product._get_main_uom()
            if not sale_uom._has_common_reference(main_uom):
                continue
            normalized_qty = sale_uom._compute_quantity(
                quantity, main_uom, round=False,
            )
            if normalized_qty <= 0:
                continue
            template_id = product.product_tmpl_id.id
            quantities[template_id] = quantities.get(template_id, 0.0) + normalized_qty
            products_by_template.setdefault(template_id, []).append(product)
        return quantities, products_by_template

    @staticmethod
    def _tl_visible_regular_templates(website, partner, quantities, products_by_template, limit):
        """Reapply the same catalog filter as /shop *before* top-N limiting.

        website.sale_product_domain is extended by the existing exclusive-
        products addon to include the logged-in customer's permissions.
        """
        if not quantities or limit <= 0:
            return request.env["product.template"]

        visible_domain = Domain.AND([
            Domain(website.sale_product_domain()),
            Domain("id", "in", list(quantities)),
        ])
        templates = request.env["product.template"].sudo().search(visible_domain)
        # For variant-restricted templates, require the default shop variant
        # to be visible too. This prevents linking to a product page whose
        # default variant the logged-in user cannot access.
        allowed_ids = []
        for template in templates:
            default_variant_id = template._get_first_possible_variant_id()
            default_variant = request.env["product.product"].sudo().browse(
                default_variant_id
            ).exists()
            if not default_variant or not default_variant._website_manufactured_accessible(partner):
                continue
            if any(
                product._website_manufactured_accessible(partner)
                for product in products_by_template.get(template.id, [])
            ):
                allowed_ids.append(template.id)
        ids = rank_visible_template_ids(quantities, allowed_ids, limit)
        # browse() preserves ranking order without an expensive custom SQL sort.
        return request.env["product.template"].sudo().browse(ids)

    @http.route()
    def user_regular_products(self, page=0, **kwargs):
        user = request.env.user
        if user._is_public():
            return request.redirect("/web/login?redirect=/shop/my_regular_products")
        website = request.env.website
        if not website.has_ecommerce_access():
            return request.redirect("/web/login?redirect=/shop/my_regular_products")
        partner = user.partner_id
        # This limit applies after filtering unauthorized and unpublished items.
        configured_limit = request.env["ir.config_parameter"].sudo().get_int(
            "website_sale_menu_partner_top_selling.limit", 10
        )
        limit = min(300, max(0, int(configured_limit)))
        quantities, products_by_template = self._tl_normalized_sales_by_product(
            website, partner
        )
        templates = self._tl_visible_regular_templates(
            website, partner, quantities, products_by_template, limit
        )
        ppg = max(1, website.shop_ppg or 21)
        ppr = max(1, website.shop_ppr or 4)
        try:
            page = max(0, int(page))
        except (TypeError, ValueError):
            page = 0
        total = len(templates)
        maximum_page = max(0, (total - 1) // ppg)
        page = min(page, maximum_page)
        products = templates[page * ppg: (page + 1) * ppg]

        # Keep the Odoo shop context: filters, categories, cart and wishlist.
        # Do not call the OCA route, as it would execute an unrestricted sudo
        # ranking and apply its limit before product authorization.
        shop_response = self.shop(page=0)
        if not hasattr(shop_response, "qcontext"):
            return shop_response

        # This is the established contract price hook, so the normal price
        # and contract offer (including strike-through) remain consistent with
        # the standard shop page. No second price calculation is introduced.
        prices = products._get_sales_prices(
            request.pricelist.with_context(self.env.context),
            request.fiscal_position.with_context(self.env.context),
            website.with_context(self.env.context),
        )
        Product = request.env["product.product"]
        first_ids = [template._get_first_possible_variant_id() for template in products]
        variants = Product.sudo().browse(
            variant_id for variant_id in first_ids if variant_id
        )
        variants.fetch()
        variants_by_id = {variant.id: variant for variant in variants}
        product_variants = dict(zip(
            products,
            (variants_by_id.get(variant_id, Product) for variant_id in first_ids),
            strict=False,
        ))
        pager = website.pager(
            url="/shop/my_regular_products",
            total=total,
            page=page + 1,
            step=ppg,
            scope=5,
        )
        values = shop_response.qcontext
        values.update({
            "pager": pager,
            "products": products,
            "search_product": products,
            "search_count": total,
            "product_variants": product_variants,
            "bins": lazy(lambda: TableCompute().process(products, ppg, ppr)),
            "products_prices": prices,
            "get_product_prices": lambda product: prices[product.id],
            "structured_data": products._render_jsonld(),
        })
        if website.google_analytics_key:
            values["product_tracking_infos"] = products._get_google_analytics_list_data_batch(
                prices, website, "My Regular Products"
            )
        return request.render("website_sale.products", values)
