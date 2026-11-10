{
    "name": "Website Sale - Blanket Contract Price and Consumption",
    "version": "20.0.1.3.0",
    "summary": "Display customer contract prices and bind cart lines to OCA sale blanket orders",
    "category": "Website/eCommerce",
    "author": "Tecniloop",
    "website": "https://github.com/jaime-roiges/oca",
    "license": "AGPL-3",
    "depends": ["website_sale", "sale_blanket_order", "website_sale_manufactured_for_partner", "tl_sale_blanket_portal"],
    "data": ["views/contract_templates.xml", "views/contract_offer_templates.xml", "views/contract_availability_templates.xml", "views/product_template_views.xml"],
    "assets": {"web.assets_frontend": [
        "tl_website_sale_blanket_contract/static/src/scss/contract_offer.scss",
        "tl_website_sale_blanket_contract/static/src/js/contract_offer.js",
    ]},
    "installable": True,
}
