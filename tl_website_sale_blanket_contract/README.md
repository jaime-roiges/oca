# Website Sale - Blanket Contract Price and Consumption

Odoo 20 integration of OCA `sale_blanket_order` with `website_sale`.

* Public visitors never obtain private contract prices.
* Authenticated clients with a unique eligible agreement see its price in
  shop listings and the selected variant page.
* Cart lines link to `sale.order.line.blanket_order_line`; the same agreement
  controls the price and quantity. Mixed contracts share the same SO.
* Ambiguous contracts are selected explicitly from the customer contract portal.
* Revalidates customer, company, currency, quantity and price at confirmation;
  locks the agreement row to limit concurrent overselling.

Requires the existing protected-product addon and `tl_sale_blanket_portal`.
The code is a QA candidate; install on Odoo 20 and test the complete website.

## Contractual offers (20.0.1.1.0)

When the authenticated customer's active contract price is lower than the
ordinary price of that customer's current website pricelist, shop tiles and
the product page show the ordinary price struck through **above** the contract
price, in the website's tax-display currency and regime.  Equal or higher
contract prices display without a false discount.  All actual cart prices
continue to come from the selected OCA blanket order line.

Multi-variant products without a selected variant are not given a misleading
single price; the comparison applies after choosing an eligible variant.
Contract prices are not shown to public visitors or unrelated customers.

The addon synchronizes the layout marker on Odoo 20 variant and quantity
changes via the product-page interaction. Verify that both the original
price and its styling update in a browser on the target website build.


## Customer-specific contractual availability on product pages (20.0.1.2.0)

On the product detail page, authenticated customers see the *remaining contractual
quantity by active blanket order line*, immediately underneath the price. No
contract data is shown to public visitors or unrelated customers. For multiple
valid contracts of the same variant, each contract and its own unit of measure
are shown, with a link to explicitly choose the contract. Exhausted contracts
are displayed as zero without a purchase link.

The balance comes from OCA ``remaining_uom_qty``. It can take draft
quotations and open carts into account and **must not be interpreted as
physical warehouse stock**. The amount is checked again on cart updates and
confirmation. Variant changes refresh the block using the same combination
RPC as the contract price.

## Contractual packagings in Odoo 20 (20.0.1.3.0)

Odoo 20 represents website sales packagings as `uom.uom` records in a
product's `uom_ids` field, not as legacy `product.packaging` records.
Enable **Units of Measure** in Odoo settings and configure, for example,
`Case of 12` with `relative_uom_id=Unit`, `relative_factor=12`, then add it
to the product's **Packagings** and publish the UoM on the target website.

The contract detail block still displays the contract balance in its original
UoM. For a selected website packaging it also shows how many complete
packagings fit and the loose remainder in the product's default UoM. The
calculation always rounds DOWN; for 1000 units and packs of 12 it displays
83 complete packs and a remainder of 4 units.

The product setting **Whole packages for contractual website sales** defaults
to enabled. For a contracted cart line sold in a packaging other than the
product's base UoM, only positive, integral packaging quantities are allowed.
This is enforced on add, quantity update, and order confirmation. It does
not restrict normal non-contract sales. Disable the setting on the product
if fractional packs are genuinely permitted. The ordinary Odoo native
website packaging chooser and prices are preserved.

The explicit contract purchase form (My Contracts) also lists the website's
allowed UoMs and remaining amounts, and submits `uom_id` to the same
server-side contract and package checks.

**Important:** contract balances may count open carts and quotations per
OCA. They are not physical inventory. Tests are included but require a
real Odoo 20 server and database to run; no runtime install is asserted.
