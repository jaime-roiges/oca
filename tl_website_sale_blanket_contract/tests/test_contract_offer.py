# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import TransactionCase, tagged

from ..models.product_template import _tl_is_contract_offer


@tagged("post_install", "-at_install")
class TestContractOfferDisplay(TransactionCase):
    def test_strikethrough_requires_real_reduction(self):
        currency = self.env.company.currency_id
        self.assertTrue(_tl_is_contract_offer(currency, 120.0, 80.0))
        self.assertFalse(_tl_is_contract_offer(currency, 80.0, 80.0))
        self.assertFalse(_tl_is_contract_offer(currency, 70.0, 80.0))

    def test_fractional_rounding_does_not_create_fake_offer(self):
        currency = self.env.company.currency_id
        self.assertFalse(_tl_is_contract_offer(currency, 80.0000001, 80.0))
