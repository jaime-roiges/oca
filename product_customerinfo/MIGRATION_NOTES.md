# Migration notes: product_customerinfo 19.0 -> 20.0

- Converted `security/ir.model.access.csv` to Odoo 20 `security/ir.access.csv` while preserving the original read / CRUD grants.
- Renamed inherited `product.supplierinfo.product_uom_id` usage to `uom_id`, matching Odoo 20.
- Adapted `product.pricelist.item._compute_price()` to the Odoo 20 signature.
- Added an explicit `_compute_base_price()` branch for the custom `base = "partner"`. Odoo 20 no longer delegates unknown bases to `product._price_compute()` and would otherwise silently use the sales price.
- Updated the discount rule mode from the removed `formula` value to Odoo 20 `discount`.
- Kept existing XML IDs and functional behavior otherwise unchanged.
