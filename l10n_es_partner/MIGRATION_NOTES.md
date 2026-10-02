# Odoo 20 migration notes

- Migrated addon version to `20.0.1.0.0`.
- Removed the Odoo 19 dependencies `base_vat` and `base_bank_from_iban`; this addon no longer
  uses either after the Odoo 20 banking model refactor.
- Odoo 20 removes the `res.bank` model. The legacy extension of `res.bank` was moved to
  `res.partner.bank` as `bank_long_name`, `bank_vat`, and `bank_website`.
- The inherited view now targets `base.view_partner_bank_form` and anchors on Odoo 20 core
  fields `bank_name` and `bank_bic`.
- Removed the Bank of Spain import wizard and its ACL/data generator because there is no
  Odoo 20 master `res.bank` model to populate.
- Replaced `ir.config_parameter.get_param()` / `set_param()` uses with the typed Odoo 20
  `get_str()` / `set_str()` API.
- Preserved the existing view XML-ID `l10n_es_partner.view_res_bank_form` while changing its
  target model to `res.partner.bank`.

Static validation does not prove installation/runtime success; test the addon in an Odoo 20
server/database after deployment.
