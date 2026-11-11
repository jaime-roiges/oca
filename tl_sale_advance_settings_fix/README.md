# tl_sale_advance_settings_fix - Odoo 20

## Purpose

Company field is empty/uneditable in the existing advance settings screen, and the customer 438 account is not persisted. This addon provides a fresh company-aware configuration form while retaining the original configuration menu and `res.company` data fields.

## Dependencies

- `account`
- `tl_sale_advance_allocation` (existing custom addon)

It modifies **only** the `action` reference on the existing menu `tl_sale_advance_allocation.menu_tl_adv_config` to point to a new settings action. The original action and view remain intact. All OCA sources remain untouched.

## Behaviour

- Opens on the currently active company by default, with editable company selection.
- Loads existing 438/407 and automatic allocation options on first open and when changing company.
- Saves directly to `res.company.tl_customer_advance_account_id`, `tl_supplier_advance_account_id`, and `tl_auto_allocate_sales`.
- Validates the account's selected-company membership, account type, and 438/407 prefix.
- Restricts save to an Accounting Manager / System Administrator who is allowed to access the selected company.
- Returns a reload so the form reopens with persisted values.

## Install

Place addon under custom addons, refresh apps list and install `tl_sale_advance_settings_fix`. Restart Odoo and update the module with `-u tl_sale_advance_settings_fix` if previously installed. Do **not** modify OCA modules.

## Manual QA checklist

1. Open the existing **Advance settings** menu with an Accounting Manager.
2. Verify Company is populated with the active company, but remains editable.
3. Select a current-liability account with the 438 prefix; click Save.
4. Reopen settings; verify the selected 438 account is still visible.
5. Switch to another allowed company: verify its own settings are loaded and saved independently.
6. Try an account outside the selected company or not starting 438; verify validation blocks it.
7. Create a customer advance invoice against a blanket contract for the configured company.
8. Verify that automatic advance allocation remains disabled unless explicitly enabled.

## Compatibility note

This is a static patch prepared against the XML IDs and company fields of the existing custom module as identified from its translations. It has NOT been executed against the user's Odoo 20 database. Check existing action customizations before deploying to production. In particular, upgrading the original `tl_sale_advance_allocation` module later may reset the original menu action; upgrade this fix addon afterward.
