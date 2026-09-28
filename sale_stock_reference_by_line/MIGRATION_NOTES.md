# Migración 19.0 → 20.0

- Versión del manifiesto: `20.0.1.0.0`.
- Sin `ir.model.access` / `ir.rule` que convertir.
- API ya alineada con Odoo 20:
  - `stock.reference` (no `procurement.group`)
  - `_prepare_procurement_values()` asigna `reference_ids`
  - `_action_launch_stock_rule(*, previous_product_uom_qty=False)` se mantiene
  - `_update_candidate_moves_list` sigue en `stock.move`
  - `sale.order.line.product_uom_id` no cambia (solo stock/purchase/mrp usan `uom_id`)
- `sale_stock` sigue existiendo en el core 20.0.
