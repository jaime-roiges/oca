# Migración 19.0 → 20.0

- Versión: `20.0.1.0.0`.
- XPath de la lista de líneas: `price_unit` vive dentro de `<column name="price_unit">` en `sale.view_order_form` (Odoo 20).
  Antes: `//field[@name='order_line']/list/field[@name='price_unit']`
  Ahora: `//field[@name='order_line']/list/column[@name='price_unit']`
