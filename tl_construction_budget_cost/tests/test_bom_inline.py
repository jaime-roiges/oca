from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestBudgetBomInline(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente coste BOM'})
        cls.product = cls.env['product.product'].create({'name': 'Partida coste BOM', 'type': 'consu'})
        cls.component = cls.env['product.product'].create({'name': 'Recurso coste BOM', 'type': 'consu', 'standard_price': 10})

    def quote_with_bom(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id, 'tl_office_percent': 13})
        line = self.env['sale.order.line'].create({'order_id': order.id, 'product_id': self.product.id, 'product_uom_qty': 2, 'price_unit': 100})
        bom = self.env['mrp.bom'].create({'product_tmpl_id': self.product.product_tmpl_id.id, 'product_qty': 1, 'uom_id': self.product.uom_id.id, 'x_original_sol_id': line.id})
        line.write({'x_bom_id': bom.id})
        component = self.env['mrp.bom.line'].create({'bom_id': bom.id, 'product_id': self.component.id, 'product_qty': 3, 'uom_id': self.component.uom_id.id})
        return order, line, bom, component

    def test_cost_is_per_quote_and_does_not_change_product(self):
        order1, line1, bom1, c1 = self.quote_with_bom()
        order2, line2, bom2, c2 = self.quote_with_bom()
        c1.tl_budget_unit_cost = 12
        c2.tl_budget_unit_cost = 20
        self.assertEqual(self.component.standard_price, 10)
        self.assertAlmostEqual(order1.tl_direct_cost, 72)
        self.assertAlmostEqual(order2.tl_direct_cost, 120)
        self.assertAlmostEqual(order1.tl_office_cost, 9.36)
        self.assertEqual(len(line1.tl_resource_ids), 1)
        self.assertAlmostEqual(line1.tl_resource_ids.unit_cost, 12)
        self.assertEqual(line1.tl_resource_ids.source_bom_line_id, c1)
        self.assertAlmostEqual(c2.tl_budget_unit_cost, 20)

    def test_quantity_change_updates_resource(self):
        order, line, bom, component = self.quote_with_bom()
        bom.action_tl_prepare_bom_costs()
        component.product_qty = 5
        self.assertEqual(line.tl_resource_ids.quantity, 5)
        self.assertAlmostEqual(order.tl_direct_cost, 100)

    def test_cost_cannot_be_saved_to_shared_template(self):
        bom = self.env['mrp.bom'].create({'product_tmpl_id': self.product.product_tmpl_id.id, 'product_qty': 1, 'uom_id': self.product.uom_id.id})
        component = self.env['mrp.bom.line'].create({'bom_id': bom.id, 'product_id': self.component.id, 'product_qty': 1, 'uom_id': self.component.uom_id.id})
        with self.assertRaises(UserError):
            component.tl_budget_unit_cost = 50
        self.assertEqual(self.component.standard_price, 10)
