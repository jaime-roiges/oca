# purchase_stock_picking_invoice_link 19.0 → 20.0

- Version 20.0.1.0.0. Fuente OCA/stock-logistics-workflow 19.0.
- uom.uom.rounding no existe en 20: float_is_zero usa decimal.precision "Product Unit".
- Depende de stock_picking_invoice_link (OCA, no migrado aquí) y purchase_stock (core).
- auto_install True conservado.
- Sin rediseño.
