{
    "name": "Dimpal - B2B Credit Checkout and OCA Blanket Contract Bridge",
    "summary": "Allow approved credit checkout; route contracted products through OCA call-offs",
    "version": "20.0.1.0.0",
    "category": "Website/eCommerce",
    "license": "AGPL-3",
    "author": "Tecniloop",
    "depends": [
        "website_sale_checkout_skip_payment",
        "website_sale_manufactured_for_partner",
        "tl_dimpal_portal_blanket",
    ],
    "data": ["views/checkout_templates.xml"],
    "installable": True,
    "application": False,
}
