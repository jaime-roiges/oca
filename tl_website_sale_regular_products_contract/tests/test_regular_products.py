# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase
from odoo.addons.tl_website_sale_regular_products_contract.controllers.ranking import (
    rank_visible_template_ids,
)


class TestSecureRegularProducts(TransactionCase):
    def test_filter_before_limit(self):
        # The highest sellers may be hidden for the current portal contact.
        quantities = {1: 500, 2: 400, 3: 300, 4: 200}
        self.assertEqual(rank_visible_template_ids(quantities, [3, 4], 1), [3])

    def test_stable_sort(self):
        self.assertEqual(rank_visible_template_ids({8: 10, 3: 10}, [8, 3], 2), [3, 8])

    def test_no_products_from_other_customers(self):
        self.assertEqual(rank_visible_template_ids({1: 200, 2: 2}, [2], 10), [2])

    def test_empty_limit(self):
        self.assertEqual(rank_visible_template_ids({1: 100}, [1], 0), [])
