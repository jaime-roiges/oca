# base_vat compatibility for Odoo 20

Odoo 20 removed the standalone `base_vat` addon.

Its Odoo 19 responsibilities were split:

- offline VAT validation and VAT-related partner infrastructure were moved into core;
- the `vat_check_vies` configuration is part of `account`;
- online VIES behavior, the `vies_valid` field, `has_foreign_fiscal_position`, the VIES cron and partner UI moved to
  `l10n_eu_account_vies`.

This module is therefore a compatibility layer, not a copy of the Odoo 19 source.
It depends on `l10n_eu_account_vies` so installing legacy addons that still require
`base_vat` gets the complete Odoo 20 VAT/VIES implementation.

Compatibility supplied here:

- legacy technical module name `base_vat`;
- `_check_vies_iap()` -> `_check_vies_validity_iap()`;
- `_cron_check_vies_iap()` -> `_cron_check_vies_validity_iap()`;
- `base_vat.view_partner_base_vat_form` compatibility view;
- `base_vat.res_config_settings_view_form` compatibility view;
- `base_vat.vies_iap_check_update` alias to the Odoo 20 cron.

For native Odoo 20 code, dependencies should still be migrated away from `base_vat`:
use `base`/`account` for offline VAT functionality and `l10n_eu_account_vies` when VIES
functionality is required.
