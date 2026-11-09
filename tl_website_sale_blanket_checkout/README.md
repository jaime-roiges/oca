# B2B credit checkout with mixed blanket-contract orders (Odoo 20)

Depends on the OCA `website_sale_checkout_skip_payment` 20.0 PR, which is **not bundled**.
On one `sale.order`, each line may refer to a different `sale.blanket.order.line` or no
blanket line at all. OCA sale_blanket_order controls contracted price, taxes and quantities.
Website auto-assignment can select only a unique active same-product blanket contract;
ambiguities require an explicit portal release request or a salesperson's choice.

The module retains the OCA `skip_website_checkout_payment` customer credit flag; it
is NOT a credit-risk scoring system. Product authorization always runs regardless
of payment method. There is no automatic creation of zero-price call-off orders.

This package has not been runtime-tested on Odoo 20 Enterprise.
