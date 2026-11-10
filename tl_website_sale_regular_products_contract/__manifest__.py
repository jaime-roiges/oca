# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Sale - Regular Products for Contract Customers",
    "version": "20.0.1.0.0",
    "summary": "Secure regular products listing with customer-only products and blanket pricing",
    "category": "Website/eCommerce",
    "website": "https://github.com/jaime-roiges/oca",
    "author": "Tecniloop",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "website_sale_menu_partner_top_selling",
        "website_sale_manufactured_for_partner",
        "tl_website_sale_blanket_contract",
    ],
    "data": ["views/templates.xml"],
}
