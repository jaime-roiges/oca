{
    "name": "Blanket Contracts - Dedicated Stock Locations",
    "version": "20.0.1.0.0",
    "summary": "Protect company-owned goods committed to one customer in internal stock locations",
    "category": "Inventory/Inventory",
    "author": "Tecniloop",
    "website": "https://github.com/jaime-roiges/oca",
    "license": "AGPL-3",
    "depends": ["tl_sale_blanket_management", "sale_stock", "purchase_stock"],
    "data": [
        "security/ir.access.csv",
        "wizard/allocate_views.xml",
        "views/blanket_stock_views.xml",
    ],
    "installable": True,
}
