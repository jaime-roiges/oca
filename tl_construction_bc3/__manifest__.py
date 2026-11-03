# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Construction BC3 Import",
    "version": "20.0.1.17.0",
    "category": "Construction",
    "summary": "Import FIEBDC-3/2024 BC3 price catalogues and budgets",
    "author": "Tecniloop",
    "license": "AGPL-3",
    "depends": ["construction_developer", "sale_management", "tl_construction_manual_field_compat"],
    "data": [
        "security/ir.access.csv",
        "views/bc3_catalog_views.xml",
        "wizard/bc3_import_wizard_views.xml",
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        "views/sale_order_context_actions.xml",
    ],
    "installable": True,
    "application": False,
    "development_status": "Beta",
    "maintainers": ["tecniloop"],
}
