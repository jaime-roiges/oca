# Website Sale - Dedicated Blanket Stock (Odoo 20)

Extends the web cart's physical-stock check for lines linked to a blanket contract
with an isolated dedicated internal location. Normal products still use the
standard `website_sale` check. Requires `tl_website_sale_blanket_contract` and
`tl_sale_blanket_stock_reservation`.

Only products with a confirmed incoming transfer to the dedicated location can
be purchased against its physical availability. The warehouse must match the
agreement's warehouse. This does not waive the contract's quantity limit.

**Important:** dynamic website stock-badges / variant stock indicators from
`website_sale_stock` and any third-party checkout extensions require on-server QA.
