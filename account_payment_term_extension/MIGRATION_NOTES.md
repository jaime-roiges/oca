# Migration notes: Odoo 19.0 -> 20.0

## Applied changes

- Module version bumped from `19.0.1.0.0` to `20.0.1.0.0`.
- Replaced `security/ir.model.access.csv` with Odoo 20 `security/ir.access.csv`.
- Preserved the three existing XML IDs and their effective permissions:
  - internal users: read
  - accounting users: read
  - accounting managers: create/read/write/delete
- Moved `security/ir.access.csv` to the end of the manifest `data` list, matching the Odoo 20 core loading pattern.
- Aligned custom `account.payment.term.line._get_due_date()` with Odoo 20 core by using
  `fields.Date.context_today(self)` when `date_ref` is empty.

## Verified as unchanged / compatible with Odoo 20 core

- `account.payment.term._compute_terms(...)` keeps the same public signature.
- `account.payment.term.line._get_due_date(date_ref)` still exists.
- Core payment-term `delay_type` values used as anchors by this module still exist.
- View XML ID `account.view_payment_term_form` still exists.
- `label for="early_discount"` and `field name="value_amount"` still exist in that view.
- Settings view XML ID `account.res_config_settings_view_form` and `<app name="account">` still exist.
- Dependencies `account` and `purchase` both still exist in Odoo 20.
- No use of removed access APIs, `odoo.osv`, QWeb `t-esc`/`t-raw`, tracking API renames,
  SQL-report hooks, `bin_size`, POS/website/payment-provider APIs, or renamed stock/purchase UoM fields was found.

## Important pre-existing risks (not changed by this migration)

1. The module fully overrides `account.payment.term._compute_terms()`. This remains compatible
   at the signature level, but it continues to shadow future fixes in the core implementation.
2. The module intentionally rejects cash rounding. `readme/ROADMAP.md` documents this limitation.
3. OCA has open fixes for two existing amount-calculation issues in this module family:
   multi-currency company/document amount swapping, and fixed-first-line percentage bases.
   They are not Odoo-20 migration requirements and therefore are not applied in this minimal port.

## Validation performed here

- Python byte-compilation.
- XML parsing of all module XML files.
- Static grep for Odoo 20 blockers from the supplied migration checklist.

## Still required in a real Odoo 20 environment

Run an installation/update against an Odoo 20 database and execute the module test suite,
including security checks for the holiday model and functional invoice-posting scenarios.
