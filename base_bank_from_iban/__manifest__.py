# Copyright 2017 Tecnativa - Carlos Dauden
# Copyright 2018-2022 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3).

{
    "name": "Bank from IBAN",
    "version": "20.0.2.0.0",
    "author": "Tecnativa, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/community-data-files",
    "category": "Localization",
    "license": "AGPL-3",
    "depends": ["account"],
    "development_status": "Mature",
    "data": ["views/res_partner_bank_views.xml"],
    "external_dependencies": {"python": ["schwifty"]},
    "installable": True,
}
