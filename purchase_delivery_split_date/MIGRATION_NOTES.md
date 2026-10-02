# Migration notes: Odoo 19.0 → 20.0

## Compatibility changes

- Bumped the addon version to `20.0.1.0.0` and removed the obsolete
  `installable` manifest key.
- Updated purchase order line test data from `product_uom_id` to `uom_id`.
- Updated the date-splitting hook for the Odoo 20 `purchase_stock` flow:
  planned incoming dates are written to `stock.move.date`, while
  `stock.move.date_deadline` is reserved for the promised/deadline date.
- Updated assertions to validate `stock.move.date`.

The addon still groups incoming pickings by the warehouse-local calendar day,
preserving the existing timezone-aware behavior. Installation and runtime tests
require an Odoo 20 server and database and were not executed here.
