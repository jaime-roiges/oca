{
    "name": "Demo Sales, Purchase and CRM Generator",
    "summary": "Generate traceable sample sales, purchases, CRM opportunities and activities",
    "version": "20.0.1.0.0",
    "category": "Extra Tools",
    "website": "https://www.odoo.com",
    "author": "Tecniloop",
    "license": "AGPL-3",
    "depends": ["sale_management", "purchase", "crm", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/demo_generation_run_views.xml",
        "views/demo_generation_wizard_views.xml",
        "views/demo_generation_menus.xml",
    ],
    "installable": True,
    "application": True,
}
