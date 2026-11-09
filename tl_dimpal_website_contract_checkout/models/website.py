# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class Website(models.Model):
    _inherit = "website"

    def _prepare_sale_order_values(self, partner_sudo):
        # OCA auto call-off conversion on normal shop orders may generate
        # zero-price releases incorrectly; contract releases have their own portal.
        values = super()._prepare_sale_order_values(partner_sudo)
        values["create_call_off_from_so_if_possible"] = False
        return values
