# Migration notes - Odoo 20

Source: `ursais/sale-workflow`, branch `19.0-mig-sale_pricelist_triple_discount`.

## Main adaptations

- Version bumped to `20.0.1.0.0`.
- Odoo 20 pricelist computation values changed from the old `percentage` / `formula` model to `discount` / `markup` / `fixed`.
- Odoo 20 no longer uses a per-pricelist `discount_policy`; whether a discount is shown separately is decided by the sale discount feature and `product.pricelist.item.is_plain_discount` / `_show_discount()`.
- Removed the 19.0 migration proposal's context manager that temporarily wrote the aggregate discount into the pricelist rule. The Odoo 20 port computes the effective triple discount locally and never mutates `price_discount` during pricing.
- `_compute_name_and_price()` is not used in Odoo 20. The price label hook is `_compute_price_label()`.
- `_compute_rule_tip()` and `_compute_is_plain_discount()` include `discount2` and `discount3`.
- Sale order lines receive the original three percentages only for a plain discount rule. For complex rules (rounding, surcharge, margins, markup), Odoo 20 standard behavior is preserved and the combined effect stays in `price_unit` to avoid double-discounting.
- The form XPath was migrated from the removed `percent_price` / old formula layout to the Odoo 20 `price_markup` row in `product.product_pricelist_item_form_view`.
- Tests were adapted from `groups_id` to `group_ids`, removed the deleted `discount_policy` assumptions, and replaced removed `check_access_rights()` with `has_access()`.

## Static validation

The delivered archive is checked for Python syntax, XML well-formedness, manifest syntax/data references, obsolete Odoo 19 pricelist APIs, and ZIP integrity. Runtime installation and functional tests still require an Odoo 20 database with `sale_triple_discount` installed.

## 20.0.1.0.1 runtime fix

- Removed `pricelist_item_id` and `pricelist_item_id.*` from the dependencies of the
  stored `discount1`/`discount2`/`discount3` compute. In Odoo 20
  `sale.order.line.pricelist_item_id` is computed and not stored, so reverse dependency
  invalidation from `product.pricelist.item` attempted an SQL domain on a field without
  SQL representation.
- The compute now depends on `discount`, `product_id`, `product_uom_id` and
  `product_uom_qty`, and reads `pricelist_item_id` only while computing.
- Restored the `sale.order._recompute_prices()` hook so changing a pricelist explicitly
  refreshes the three displayed discount fields after the core price recomputation.
