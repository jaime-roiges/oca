# Migración 19.0 → 20.0

- Versión: `20.0.1.0.1`.
- `ir.model.access.csv` → `ir.access.csv` para el wizard `sale.exception.confirm` (grupo salesman, operación `crud`).
- El CSV de acceso va al final de `data`.
- Sigue dependiendo de `base_exception` (OCA, no core).
- Anclas verificadas en Odoo 20:
  - `sale.res_config_settings_view_form` y `<setting id="order_warnings">`
  - `sale.view_order_form`, `sale.view_order_tree`, `sale.view_quotation_tree`
  - `sale.view_sales_order_filter` / `my_sale_orders_filter`
  - `sale.menu_sales_config`
  - `res.partner.sale_warn_msg` y `virtual_available_at_date` en líneas (core `sale`)
