from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestCheapestCarrier(TransactionCase):
    def test_select_lowest_successful_quote(self):
        order = self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Shipping test'}).id,
        })
        carriers = self.env['delivery.carrier'].search([], limit=2)
        if len(carriers) != 2:
            self.skipTest('Two delivery methods required for comparison')
        with patch.object(type(order), '_tl_rate_carriers', return_value=[
            (carriers[1], 5.0, True, ''),
            (carriers[0], 7.0, True, ''),
        ]):
            self.assertEqual(order._tl_best_carrier(carriers)[0], carriers[1])
