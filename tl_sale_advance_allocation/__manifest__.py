{
    "name": "Blanket Contracts - Fiscal Advances",
    "summary": "Allocate posted customer/supplier advance invoices across mixed-contract invoices",
    "version": "20.0.1.0.0",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "author": "Tecniloop",
    "website": "https://github.com/jaime-roiges/oca",
    "depends": ["tl_sale_blanket_management", "account"],
    "data": [
        "security/ir.access.csv", "views/advance_views.xml",
        "wizard/advance_register_views.xml", "wizard/advance_apply_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
}
