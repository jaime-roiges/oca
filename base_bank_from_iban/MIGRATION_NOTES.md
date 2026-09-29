# Migration notes: Odoo 19.0 -> 20.0

This version is a functional migration following Odoo 20 core's bank-account model.

## Architectural change

Odoo 20 removes `res.bank` and the `res.partner.bank.bank_id` relationship. Bank metadata
is stored directly on `res.partner.bank` (`bank_name`, `bank_bic`, `country_id`, etc.).
The standalone `base_iban` module also disappears; IBAN validation/type detection lives in
`account` / `odoo.tools.bank_account_number`.

Accordingly this addon no longer creates or searches `res.bank` records. Schwifty enriches
the current `res.partner.bank` directly.

## Changes

- dependency: `base_iban` -> `account`
- `acc_number` -> `account_number`
- `acc_type` -> `account_type`
- removed `bank_id` / `res.bank` usage
- removed inheritance of obsolete `base.view_res_bank_form` and tree view
- new `bank_code` field on `res.partner.bank` preserves the former bank-code information
- IBAN lookup now fills `bank_name`, `bank_bic`, `bank_code`, and `country_id`
- removed the legacy `account.setup.bank.manual.config` extension; that old flow is not part
  of the Odoo 20 implementation used by this addon
- tests rewritten around `res.partner.bank`

## Behaviour

Explicitly supplied bank metadata is preserved. Schwifty only fills missing values.
Invalid/non-IBAN account numbers are left untouched and do not create auxiliary records.
