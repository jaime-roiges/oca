# product_brand_purchase 19.0 → 20.0

- Rama OCA/brand 19.0.
- ACL XML/CSV → ir.access.csv; reglas a domain.
- t-esc→t-out; report_file fuera.
- Sin rediseño.

## 2026-09-29 follow-up

- Migrated `purchase.report` extension from removed `_select()` / `_group_by()` hooks to `_select_list()` / `_groupby_list()` using `TableSQL`.
