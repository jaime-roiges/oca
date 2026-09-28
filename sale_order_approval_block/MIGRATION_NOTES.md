# Migración 19.0 → 20.0

- Versión: `20.0.1.0.0`.
- `security/ir.model.access.csv` → `security/ir.access.csv` (modelo `sale.approval.block.reason`).
- Grupos XML al inicio de `data`; `ir.access.csv` al final.
- Sin `ir.rule`.
- Depende de `sale_exception` (OCA, no core). Hay que tenerlo también en 20.0.
- Anclas de vista `sale.view_order_form` (`date_order`, `action_confirm`) y `sale.view_sales_order_filter` (`my_sale_orders_filter`) siguen en Odoo 20.
