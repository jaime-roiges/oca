{
    "name": "Base VAT Compatibility",
    "summary": "Odoo 20 compatibility layer for the removed base_vat addon",
    "version": "20.0.2.0.0",
    "category": "Accounting/Accounting",
    "author": "Odoo S.A., migration compatibility",
    "website": "https://github.com/odoo/odoo",
    "license": "LGPL-3",
    "depends": ["l10n_eu_account_vies"],
    "data": [
        "views/compat_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
