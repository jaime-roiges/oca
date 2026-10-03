Create a new purchase order and add discounts in any of the three discount fields.
They are applied successively: discount 2 is applied after discount 1 and discount 3
after discount 2. Negative values act as charges.

When a purchase order is confirmed for a product that does not yet have the vendor
registered, the addon preserves the Odoo 19 behavior and creates the corresponding
vendor pricelist entry with the three discounts. Vendor pricelists and vendor defaults
can also be edited directly.
