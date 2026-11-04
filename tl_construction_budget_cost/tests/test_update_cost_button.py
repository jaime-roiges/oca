from odoo.tests import tagged
from odoo.exceptions import UserError
from .test_bom_inline import TestBudgetBomInline


@tagged('post_install', '-at_install')
class TestUpdateCostsAction(TestBudgetBomInline):
    def test_header_comparison_and_action_preserve_price(self):
        order, line, bom, component = self.quote_with_bom()
        component.tl_budget_unit_cost = 12
        line.write({'price_unit': 127.14, 'purchase_price': 1})
        open_action = self.env.ref('construction_developer.action_view_sale_order_line_bom_list')
        apply_action = self.env.ref('construction_developer.action_update_sol_cost_price_margin_on_x_bom_id_write')
        result = open_action.with_context(active_model='sale.order', active_id=order.id, active_ids=order.ids).run()
        self.assertEqual(result['res_model'], 'sale.order.line')
        self.assertAlmostEqual(line.tl_effective_bom_cost, 40.68, places=2)
        self.assertTrue(line.x_different_bom_cost)
        apply_action.with_context(active_model='sale.order.line', active_id=line.id, active_ids=line.ids).run()
        self.assertAlmostEqual(line.purchase_price, 40.68, places=2)
        self.assertAlmostEqual(line.price_unit, 127.14, places=2)
        open_action.with_context(active_model='sale.order', active_id=order.id, active_ids=order.ids).run()
        self.assertFalse(line.x_different_bom_cost)
        self.assertEqual(self.component.standard_price, 10)

    def test_changed_upstream_action_fails_closed(self):
        order, line, bom, component = self.quote_with_bom()
        component.tl_budget_unit_cost = 12
        action = self.env.ref('construction_developer.action_update_sol_cost_price_margin_on_x_bom_id_write')
        action.write({'code': 'for sol in records: sol.write({"price_unit": 999})'})
        with self.assertRaises(UserError):
            action.with_context(active_model='sale.order.line', active_id=line.id, active_ids=line.ids).run()

    def test_mixed_batch_only_reprices_standard_line(self):
        order, protected, bom, component = self.quote_with_bom()
        component.tl_budget_unit_cost = 12
        other_order = self.env['sale.order'].create({'partner_id': self.partner.id})
        standard_product = self.env['product.product'].create({'name': 'Standard BoM product', 'type': 'consu'})
        standard_line = self.env['sale.order.line'].create({'order_id': other_order.id, 'product_id': standard_product.id, 'product_uom_qty': 1, 'price_unit': 100})
        standard_bom = self.env['mrp.bom'].create({'product_tmpl_id': standard_product.product_tmpl_id.id, 'product_qty': 1, 'uom_id': standard_product.uom_id.id})
        self.env['mrp.bom.line'].create({'bom_id': standard_bom.id, 'product_id': self.component.id, 'product_qty': 1, 'uom_id': self.component.uom_id.id})
        standard_line.write({'x_bom_id': standard_bom.id})
        protected.write({'price_unit': 127.14})
        initial_margin = standard_line.margin_percent
        standard_cost = standard_bom.x_bom_cost
        lines = protected | standard_line
        action = self.env.ref('construction_developer.action_update_sol_cost_price_margin_on_x_bom_id_write')
        action.with_context(active_model='sale.order.line', active_id=protected.id, active_ids=lines.ids).run()
        self.assertAlmostEqual(protected.price_unit, 127.14)
        self.assertAlmostEqual(protected.purchase_price, 40.68, places=2)
        self.assertAlmostEqual(standard_line.purchase_price, standard_cost, places=2)
        if 1 - initial_margin:
            self.assertAlmostEqual(standard_line.price_unit, standard_cost / (1 - initial_margin), places=2)

    def test_ordinary_action_not_modified_when_no_budget(self):
        other_order = self.env['sale.order'].create({'partner_id': self.partner.id})
        standard_product = self.env['product.product'].create({'name': 'Sin presupuesto propio', 'type': 'consu'})
        line = self.env['sale.order.line'].create({'order_id': other_order.id, 'product_id': standard_product.id, 'product_uom_qty': 1, 'price_unit': 80})
        bom = self.env['mrp.bom'].create({'product_tmpl_id': standard_product.product_tmpl_id.id, 'product_qty': 1, 'uom_id': standard_product.uom_id.id})
        self.env['mrp.bom.line'].create({'bom_id': bom.id, 'product_id': self.component.id, 'product_qty': 1, 'uom_id': self.component.uom_id.id})
        line.write({'x_bom_id': bom.id})
        margin, cost = line.margin_percent, bom.x_bom_cost
        action = self.env.ref('construction_developer.action_update_sol_cost_price_margin_on_x_bom_id_write')
        action.with_context(active_model='sale.order.line', active_id=line.id, active_ids=line.ids).run()
        self.assertAlmostEqual(line.purchase_price, cost, places=2)
        if 1 - margin:
            self.assertAlmostEqual(line.price_unit, cost / (1 - margin), places=2)
