# Migration notes: 19.0 -> 20.0

## Source

Migrated from OCA `account-invoicing` branch `19.0`, addon
`account_invoice_triple_discount`.

## Odoo 20 changes

- Manifest version bumped to `20.0.1.0.0`.
- The `account.move.line.discount` field still exists in Odoo 20 and is still passed by
  `account.move` to the tax base-line computation, so the aggregate-discount design is
  preserved.
- The invoice form locators were checked against Odoo 20 `account.view_move_form`; both
  the invoice-line list and embedded form still expose a `discount` field. The list XPath
  deliberately uses `//` to remain safe around Odoo 20 list `<column>` wrappers.
- `account.report_invoice_document` changed in Odoo 20. The original 19.0 report override
  for `line_colspan` was no longer safe because Odoo 20 has separate regular-line and
  grouped/collapsed-line colspan expressions. Both paths are now handled explicitly.
- The grouped/collapsed invoice-report branch now has three placeholder discount cells,
  keeping the report table aligned when triple discount columns are enabled.
- QWeb output uses `t-out`; no removed `t-esc` / `t-raw` directives remain.

## Static validation

- Python compilation.
- XML parsing.
- Manifest parsing and referenced-file checks.
- Obsolete-pattern scan for the Odoo 19 -> 20 changes relevant to this addon.

Installation and runtime behavior still need to be exercised on an Odoo 20 database.
