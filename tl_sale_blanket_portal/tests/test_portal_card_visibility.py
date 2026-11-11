# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestSupplyPortalCardVisible(TransactionCase):
    def test_contracts_card_visible_without_contract_count(self):
        """Native portal.entry visibility must not depend on JS or a counter."""
        entry = self.env.ref("tl_sale_blanket_portal.portal_entry_supply_contracts")
        self.assertEqual(entry.placeholder_count, "tl_supply_contract_count")
        self.assertEqual(entry.url, "/my/contracts")
        self.assertTrue(entry.show_in_portal)
        self.assertFalse(entry.is_config_card)
        self.assertIn(entry, entry._filter_visible_portal_cards())

    def test_extension_does_not_expose_unrelated_entry(self):
        """The extra visible card must belong to the recordset being filtered."""
        entry = self.env.ref("tl_sale_blanket_portal.portal_entry_supply_contracts")
        other_entries = self.env["portal.entry"].search([("id", "!=", entry.id)])
        self.assertNotIn(entry, other_entries._filter_visible_portal_cards())
