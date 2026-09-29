# mis_builder 19.0 → 20.0

- Version `20.0.1.2.1`. Fuente OCA/mis-builder 19.0.
- `ir.model.access.csv` → `ir.access.csv` (al final de `data`).
- `ir.rule` multi-compañía → restricción global `ir.access` (sin grupo).
- Quitado `report_file` de `ir.actions.report`.
- Depende de `account`, `board` (core) y OCA `report_xlsx` + `date_range` (ya en este lote).
- Sin rediseño.

- 20.0: compile_codeobj no está en odoo.tools.safe_eval.__all__; import desde odoo.tools.safe_eval.evaluation.
