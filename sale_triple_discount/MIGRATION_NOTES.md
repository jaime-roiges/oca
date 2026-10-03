# Migration notes — sale_triple_discount 17.0 -> 20.0

## Source

- Requested source: OCA/sale-workflow `17.0/sale_triple_discount`.
- OCA 19.0 migration PR #3965 was used as an intermediate reference for the core
  computed-discount refactor, pricelist synchronization, combo-line precompute handling,
  and the standard discount wizard integration.
- Odoo 20 Community `sale` source is the final API/view/report reference.

## Odoo 20 changes applied

- Manifest bumped to `20.0.1.0.0`.
- `tree` view locators migrated to `list` and group references use
  `sale.group_discount_per_so_line`.
- Adapted to Odoo 20's computed `sale.order.line.discount` while keeping the precise
  aggregate percentage (`digits=None`).
- Pricelist-generated discounts are synchronized into `discount1`.
- Combo item creation is deferred until the parent line is linked, avoiding precompute
  singleton failures.
- Standard `sale.order.discount` per-line discount action synchronizes `discount1` and
  clears `discount2`/`discount3`; Odoo 20's `_get_discountable_order_lines()` is used.
- `_prepare_invoice_line()` removes the core aggregate `discount` value and propagates
  the triple fields to `account_invoice_triple_discount`.
- Additive sale discounts are preserved from 17.0. Since the invoice dependency has no
  additive mode, an additive triple is flattened to one equivalent invoice discount so
  sale/invoice untaxed, tax and total amounts remain identical.
- Sale report inheritance was rebuilt for Odoo 20's `lines_to_report`, dynamic
  `colspan_count`, `td_product_discount`, and collapsed/grouped section rows.
- Tests were adapted to `tax_ids`, Odoo 20 `_recompute_prices()`, the standard discount
  wizard, and combo lines.

## Runtime verification still required

Static checks cannot prove installation/runtime behavior. Install/update on an Odoo 20
server with the Odoo 20 `account_invoice_triple_discount` dependency and exercise at least:

1. multiplicative and additive sale lines;
2. invoice creation and totals;
3. pricelist discounts and quantity changes;
4. Discount wizard (On All Order Lines);
5. quotation PDF with normal and collapsed sections;
6. combo products.
