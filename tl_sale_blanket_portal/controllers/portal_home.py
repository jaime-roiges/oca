# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Odoo 20 portal.entry counter for signed-in supply contract customers."""

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request

from .main import portal_contract_domain


class SupplyContractPortalHome(CustomerPortal):
    def _prepare_portal_counter_values(self, counter):
        """Only expose the current customer's contracts on the active website.

        Odoo 20 computes portal.entry counters asynchronously via /my/counters.
        ``sudo`` is safe here only because the shared domain is restrictive.
        """
        if counter == "tl_supply_contract_count":
            return (
                "sale.blanket.order",
                portal_contract_domain(request.env),
                "sudo",
            )
        return super()._prepare_portal_counter_values(counter)
