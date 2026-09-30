# Migration notes: base_vat 19.0 -> Odoo 20

## Why this module is a compatibility layer

The Odoo 19 `base_vat` addon no longer exists as a standalone addon in Odoo 20.
Copying its Python code into 20 would duplicate VAT constraints and VIES logic already
provided by Odoo 20.

## Odoo 20 mapping

| Odoo 19 base_vat responsibility | Odoo 20 location |
| --- | --- |
| Offline VAT validation / normalization | core (`base`) |
| `res.company.vat_check_vies` | `account` |
| `res.config.settings.vat_check_vies` | `account` |
| settings node `vies_service_setting` | `account.res_config_settings_view_form` |
| `res.partner.vies_valid` | `l10n_eu_account_vies` |
| `res.partner.perform_vies_validation` | `l10n_eu_account_vies` |
| `res.country.has_foreign_fiscal_position` | `l10n_eu_account_vies` |
| VIES IAP calls / status update | `l10n_eu_account_vies` |
| VIES cron | `l10n_eu_account_vies.vies_iap_check_update` |
| partner VIES UI | `l10n_eu_account_vies.view_partner_l10n_eu_account_vies_form` |

## Renamed methods bridged by this compatibility module

- `_check_vies_iap()` -> `_check_vies_validity_iap()`
- `_cron_check_vies_iap()` -> `_cron_check_vies_validity_iap()`

The following VIES helper names remain available in Odoo 20 and are not redefined here:
`_get_iap_vies_credentials`, `_get_iap_vies_endpoint`, `_check_vies_update_iap`,
`_update_vies_status`.

## Legacy XML-IDs

The compatibility module preserves:

- `base_vat.view_partner_base_vat_form`
- `base_vat.res_config_settings_view_form`
- `base_vat.vies_iap_check_update` (alias to the Odoo 20 cron)

On an upgraded database, if the old Odoo 19 cron still exists as a separate record it is
deactivated before the legacy XML-ID is repointed, preventing duplicate VIES polling.

## Important limitation

This is API/XML-ID compatibility for the public surface identified above. Code importing
private implementation objects directly from old source paths such as
`odoo.addons.base_vat.controllers...` or relying on removed implementation details must
still be migrated explicitly.
