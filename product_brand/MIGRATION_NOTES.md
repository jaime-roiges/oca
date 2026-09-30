# Odoo 20 migration

- Product Brands menu now hangs from `sale.product_menu_catalog`; `sale.prod_config_main` no longer exists.
- `sale.report` extension migrated from `_select_additional_fields`/`_group_by_sale` to `_select_dict`/`_groupby_list` with `TableSQL`.
- `account.invoice.report` extension migrated from `_select`/`_group_by` to `_select_list` with `TableSQL`.
- Security uses `ir.access.csv` and is loaded after views.
