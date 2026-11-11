# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from types import SimpleNamespace

from odoo.tests.common import TransactionCase

from ..controllers.main import portal_contract_domain


class TestSupplyContractPortalHome(TransactionCase):
    def test_odoo20_portal_card(self):
        entry = self.env.ref("tl_sale_blanket_portal.portal_entry_supply_contracts")
        self.assertEqual(entry._name, "portal.entry")
        self.assertEqual(entry.url, "/my/contracts")
        self.assertEqual(entry.placeholder_count, "tl_supply_contract_count")
        self.assertTrue(entry.show_in_portal)

    def test_portal_counter_and_listing_share_restrictive_domain(self):
        # Fake environment avoids an HTTP dependency while checking the exact
        # company and commercial partner scoping used in all portal routes.
        fake_env = SimpleNamespace(
            user=SimpleNamespace(partner_id=SimpleNamespace(
                commercial_partner_id=SimpleNamespace(id=101))),
            website=SimpleNamespace(company_id=SimpleNamespace(id=202)),
        )
        self.assertEqual(portal_contract_domain(fake_env), [
            ("tl_portal_visible", "=", True),
            ("confirmed", "=", True),
            ("partner_id", "child_of", 101),
            ("company_id", "=", 202),
        ])
