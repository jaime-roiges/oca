# Migración 19.0 → 20.0

- Versión del manifiesto: `20.0.1.0.x`.
- En `stock.move.line` el campo `product_uom_id` se ha renombrado a `uom_id`. `sale.order.line.product_uom_id` no cambia.
- `uom.uom.rounding` ya no existe en Odoo 20. `float_compare` usa `precision_digits` de `Product Unit`.
