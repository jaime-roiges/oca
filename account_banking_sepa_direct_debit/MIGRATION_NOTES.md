# Migración 19.0 → 20.0

- Versión: `20.0.1.1.1`.
- QWeb: `t-esc` → `t-out` en el informe de mandato (compilador QWeb 20 eliminó `t-esc`/`t-raw`).
- Sin `ir.model.access` / `ir.rule` propios.
- Depende de `account_banking_pain_base` y `account_banking_mandate` (OCA bank-payment). Hay que tenerlos también en 20.0.

- `ir.actions.report.report_file` eliminado (ya no existe en Odoo 20; basta `report_name`).
