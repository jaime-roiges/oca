from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestBudgetCost(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Cost test partner'})
        cls.resource = cls.env['product.product'].create({'name': 'Resource for budget', 'type': 'consu', 'standard_price': 20.0})
        cls.item = cls.env['product.product'].create({'name': 'Work item for budget', 'type': 'service', 'list_price': 100.0})

    def make_order(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id, 'tl_office_percent': 13.0})
        line = self.env['sale.order.line'].create({'order_id': order.id, 'product_id': self.item.id, 'product_uom_qty': 2.0, 'price_unit': 100.0})
        return order, line

    def test_independent_costs_and_overhead(self):
        order, line = self.make_order()
        other, other_line = self.make_order()
        Resource = self.env['tl.construction.budget.resource']
        r1 = Resource.create({'sale_line_id': line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 3, 'unit_cost': 10})
        Resource.create({'sale_line_id': other_line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 3, 'unit_cost': 25})
        self.assertAlmostEqual(order.tl_direct_cost, 60)
        self.assertAlmostEqual(order.tl_office_cost, 7.8)
        self.assertAlmostEqual(order.tl_budget_total, 67.8)
        self.assertAlmostEqual(other.tl_direct_cost, 150)
        r1.unit_cost = 12
        self.assertAlmostEqual(order.tl_direct_cost, 72)
        self.assertAlmostEqual(other.tl_direct_cost, 150)
        self.assertEqual(self.resource.standard_price, 20)
        order.tl_office_percent = 10
        self.assertAlmostEqual(order.tl_office_cost, 7.2)

    def test_apply_cost_preserves_sales_price(self):
        order, line = self.make_order()
        self.env['tl.construction.budget.resource'].create({'sale_line_id': line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 3, 'unit_cost': 10})
        order.action_tl_apply_budget_costs()
        self.assertAlmostEqual(line.purchase_price, 33.9)
        self.assertEqual(line.price_unit, 100)

    def test_confirmation_snapshots_and_locks(self):
        order, line = self.make_order()
        resource = self.env['tl.construction.budget.resource'].create({'sale_line_id': line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 3, 'unit_cost': 10})
        order.action_confirm()
        self.assertTrue(order.tl_snapshot_recorded)
        self.assertAlmostEqual(order.tl_snapshot_direct, 60)
        self.assertAlmostEqual(order.tl_snapshot_office, 7.8)
        with self.assertRaises(UserError):
            resource.write({'unit_cost': 11})
        with self.assertRaises(UserError):
            order.write({'tl_office_percent': 14})

    def test_zero_is_a_valid_budget_cost(self):
        order, line = self.make_order()
        self.env['tl.construction.budget.resource'].create({'sale_line_id': line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 2, 'unit_cost': 0})
        self.assertEqual(order.tl_direct_cost, 0)
        self.assertEqual(self.resource.standard_price, 20)

    def test_quotation_copy_has_independent_resources(self):
        order, line = self.make_order()
        self.env['tl.construction.budget.resource'].create({'sale_line_id': line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 3, 'unit_cost': 10})
        copied = order.copy()
        self.assertEqual(len(copied.tl_resource_ids), 1)
        self.assertEqual(copied.tl_resource_ids.order_id, copied)
        copied.tl_resource_ids.unit_cost = 15
        self.assertAlmostEqual(order.tl_direct_cost, 60)
        self.assertAlmostEqual(copied.tl_direct_cost, 90)

    def test_subcent_component_cost_is_not_rounded_to_zero(self):
        order, line = self.make_order()
        line.product_uom_qty = 1000
        self.env['tl.construction.budget.resource'].create({'sale_line_id': line.id, 'product_id': self.resource.id, 'name': 'Resource', 'quantity': 0.001, 'unit_cost': 2})
        self.assertAlmostEqual(line.tl_direct_unit_cost, 0.002, places=5)
        self.assertAlmostEqual(order.tl_direct_cost, 2.0, places=2)
