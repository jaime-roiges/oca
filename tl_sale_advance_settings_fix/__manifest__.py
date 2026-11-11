{
    "name": "Advance Accounting Settings - Company Fix",
    "summary": "Odoo 20: persist contract advance accounts per company",
    "version": "20.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Tecniloop",
    "license": "AGPL-3",
    "depends": ["account", "tl_sale_advance_allocation"],
    "data": [
        "security/ir.model.access.csv",
        "views/advance_company_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
