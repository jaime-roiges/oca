# Website Sale Regular Products for Contract Customers (Odoo 20)

Bridge for OCA `website_sale_menu_partner_top_selling` and existing Odoo 20
contract/exclusive-product extensions. Licensed AGPL-3.0.

## Behavior

- `/shop/my_regular_products` displays products regularly purchased by the
  logged-in commercial company, ranked by confirmed sale quantities.
- Sale quantities are normalized per product unit before ranking (boxes vs.
  units); draft quotations and unconfirmed blanket orders are not counted.
- Uses the same `website.sale_product_domain()` as `/shop`, including customer
  exclusivity restrictions implemented by `website_sale_manufactured_for_partner`.
- Filters **before** selecting the top N products, so authorized low-rank
  products are not hidden behind an unavailable high-rank product.
- Uses `product.template._get_sales_prices`, so contracted prices, price
  comparisons and customer pricelists stay aligned with the existing catalog.
- Existing contract selection, cart consumption, UoM/packaging and dedicated
  stock extensions remain responsible for checkout; they are not replaced.
- Do not expose other customers' contracts or past orders. The menu is hidden
  from public users, and the route checks login again server-side.

## Limitations

- Only previously sold products are included. A contract line that has never
  generated a confirmed sale does not automatically rank as a regular product.
- If the default variant of a template is inaccessible, the entire template is
  hidden rather than showing a link leading to an inaccessible product page.
- Catalog cards with multiple variants use Odoo's standard variant/base price;
  the selected variant's contract price is shown on the product detail page.
- Tested by static checks only. Odoo 20 live installation and browser tests
  remain necessary.
