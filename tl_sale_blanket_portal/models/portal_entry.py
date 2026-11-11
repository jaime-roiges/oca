# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Make the supply contract portal card visible independently of counters.

Odoo 20 renders portal.entry records with d-none unless its business visibility
filter allows the entry. JavaScript then unhides some cards if counters are > 0.
The supply-contract entry is a navigation link, and must not disappear when the
customer has no confirmed contract or the asynchronous counter fails.

The underlying /my/contracts routes enforce partner/company visibility; making
this navigation link visible never grants access to sale.blanket.order records.
"""

from odoo import models


class PortalEntry(models.Model):
    _inherit = "portal.entry"

    def _filter_visible_portal_cards(self):
        visible_cards = super()._filter_visible_portal_cards()
        contracts_card = self.env.ref(
            "tl_sale_blanket_portal.portal_entry_supply_contracts",
            raise_if_not_found=False,
        )
        if contracts_card and contracts_card in self:
            visible_cards |= contracts_card
        return visible_cards
