# Migration notes: Odoo 19.0 -> 20.0

## Applied changes

- Bumped module version to `20.0.1.0.0`.
- Migrated `ir.model.access.csv` and the global `ir.rule` to Odoo 20 `security/ir.access.csv`.
  - Internal users keep read-only access.
  - `account.group_account_invoice` keeps CRUD access.
  - The multi-company domain remains a global CRUD restriction.
- Moved `security/ir.access.csv` to the end of the manifest `data` list.
- Removed the obsolete `account.invoice.report._where()` override. Odoo 20 builds this report through `_table_sql` / `_select_list()` and directly searches `account.move.line` with `display_type = 'product'`.
- Replaced QWeb `t-esc` with `t-out`.
- Added the Odoo 20 core dependencies `tax_totals` and `state` to the custom `account.move._compute_amount()` dependency list.

## Compatibility checks

- `account.view_move_form`, `invoice_payment_term_id`, `tax_totals`, and `other_tab` are still present in Odoo 20.
- `account.report_invoice_document` still calls `account.document_tax_totals`.
- `account.account_invoicing_menu` is still present.
- `account.move._check_balanced()` and `_sync_dynamic_lines()` remain available.
- The global-discount journal items intentionally remain ordinary product-like invoice lines. Odoo 20's native `display_type='discount'` belongs to a different discount-allocation mechanism and is not a drop-in replacement for this addon's global discount lines.

## Runtime validation

Static validation is included in the migration. A real installation/update against an Odoo 20 database remains the definitive integration test.
