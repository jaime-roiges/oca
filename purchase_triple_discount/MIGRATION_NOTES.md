# Migration notes — purchase_triple_discount 19.0 -> 20.0

## Odoo 20 adaptations

- Version bumped to `20.0.1.0.0`.
- `purchase.order.line.product_uom_id` was migrated to `uom_id` in Python and tests.
- The line price/discount recomputation now reuses Odoo 20 `_get_seller_info()`.
- `_prepare_purchase_order_line()` was adapted to the Odoo 20 signature and seller-selection context.
- Triple discounts are propagated through `_prepare_account_move_line()` to the migrated
  `account_invoice_triple_discount` dependency.
- Odoo 20 removed `purchase.order._prepare_supplier_info()` and
  `_add_supplier_to_product()` from core. This addon locally reintroduces the Odoo 19
  confirmation behavior so that a missing vendor pricelist is still created with
  discount1/discount2/discount3. Its UoM key is adapted to Odoo 20 `uom_id`.
- The obsolete core sync hook `_get_po_to_supplierinfo_synced_fields()` is retained only
  as an optional compatibility extension point and no longer assumes a core super method.
- The aggregated `discount` uses full float precision (`digits=None`) to avoid rounding
  a value such as 24.7885% before tax/subtotal calculations.
- The invoicing test uses Odoo 20 `purchase.order.action_create_invoice()` instead of the
  removed invoice purchase autocomplete onchange.

## Views checked against Odoo 20

- `product.product_supplierinfo_form_view`: field `discount` still exists.
- `product.product_supplierinfo_tree_view`: field `discount` still exists.
- `purchase.purchase_order_form`: the order-line list still contains field `discount`.
- `purchase.view_partner_property_form`: field `buyer_id` still exists.

## Static validation

The package is checked with Python compilation, XML parsing, manifest evaluation,
manifest file existence, obsolete-pattern greps and ZIP integrity. No Odoo server or
database installation is executed by this migration workflow; runtime installation and
functional behavior must still be tested on an Odoo 20 database.
