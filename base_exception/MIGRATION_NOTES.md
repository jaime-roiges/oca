# Migración 19.0 → 20.0

- Versión: `20.0.1.0.0`.
- `ir.model.access.csv` → `ir.access.csv`:
  - `exception.rule`: `base.group_user` = `r`; `group_exception_rule_manager` = `crud`
  - `base.exception`: mismos grupos/operaciones
- Grupos XML al inicio de `data`; `ir.access.csv` al final.
- Python ya usaba `from odoo.fields import Domain` (válido en 20).
- Depende solo de `base_setup` (core 20).

- `env.registry.clear_cache()` no existe en 20 → `env.transaction.invalidate_ormcache()`.
