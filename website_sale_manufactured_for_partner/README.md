# Website Sale - Manufactured for Customer Visibility (Odoo 19)

Two addons are supplied:

1. `product_sale_manufactured_for` is a **minimal 19.0 compatibility implementation** of the 18.0 OCA data field. It is **not** a complete upstream migration (in particular, its sale order UI behavior is omitted). If a validated 19.0 upstream port is installed, use that instead; do not replace an installed module with this without a migration review.
2. `website_sale_manufactured_for_partner` adds website restrictions.

## Behavior

- A variant with no `manufactured_for_partner_ids` can be purchased by any visitor.
- A variant with customers assigned can be purchased only by a logged-in contact named in the field or whose `commercial_partner_id` is named there.
- Product template listings are restricted when **any** variant is assigned a customer; the template is visible only if at least one assigned customer matches the contact or company. This conservative policy can hide an unrestricted variant when another variant is restricted; it prevents leaking restricted product information.
- Catalog/search filtering is applied via `website.sale_product_domain`.
- The individual `/shop/product` route rejects direct visits with 404.
- Cart updates are checked against the actual selected variant.
- Back-office sale orders are not filtered by this addon.
- No dependency on ForgeFlow's website sale contact addon is needed; the standard `commercial_partner_id` linkage is used.

## Installation

Copy both directories into an Odoo 19 addons path. Update the app list and install `website_sale_manufactured_for_partner`. The other addon is installed as a dependency. If an official 19.0 OCA `product_sale_manufactured_for` is already available, install that version instead of the bundled compatibility addon.

On product variants (`product.product`) fill in **Manufactured for**. For a whole company, select the commercial company; its child contacts will automatically be eligible. If a single contact must be permitted exclusively, select that contact only. Product visibility is computed at template level; product variants are controlled independently when added to the cart.

## Security and limitations

This is not a record-rule boundary: an unrestricted JSON-RPC endpoint, sitemap, custom snippet, recommendations, public API, or custom theme may still expose metadata. Do not use for confidential catalog information without auditing all website routes and integrations. In particular review `/shop` autocomplete, sitemap, cart update and checkout flows, and any custom widgets in staging. The implementation is delivered as source code and passes syntax checks only; it has **not** been installation-tested on a running Odoo 19 instance.

Site-specific caches/CDN pages must not serve one logged-in user's filtered content to another user.

This release assumes the Odoo 19.0 website API retains `website.sale_product_domain`, `WebsiteSale.product`, and `sale.order._cart_update` hooks; verify signatures against the installed Odoo revision before production deployment.

License: AGPL-3. Author of the website bridge: Tecniloop.
