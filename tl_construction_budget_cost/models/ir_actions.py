# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Adapt exactly the two Construction Developer server actions, without editing them."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

# Fingerprints of the actions shipped in the supplied staging source. If the
# customer has edited either action or an update changes it, fail closed.
_APPLY = "for sol in records: sol.write({'margin_percent': sol.margin_percent, 'purchase_price': (cost := sol.x_bom_id.x_bom_cost), 'price_unit': cost / div if (div := (1 - sol.margin_percent)) else 0})"
_OPEN = """for sol in record.order_line: sol['x_different_bom_cost'] = float_compare(sol.x_bom_id.x_bom_cost, sol.purchase_price, precision_digits=2) if sol.x_bom_id else False

action = env.ref('construction_developer.window_action_view_sale_order_line_bom_list').read()[0]
action['domain'] = [('x_bom_id', '!=', False), ('id', 'in', record.order_line.ids)]"""


def _normalized(code):
    return '\n'.join(line.strip() for line in (code or '').splitlines() if line.strip())


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    tl_effective_bom_cost = fields.Float(string='Quotation cost and overhead', digits=(16, 8), compute='_compute_tl_effective_bom_cost', groups='sales_team.group_sale_manager')
    tl_has_budget_resources = fields.Boolean(string='Has quotation resources', compute='_compute_tl_effective_bom_cost', groups='sales_team.group_sale_manager')

    @api.depends('tl_resource_ids.amount_unit', 'order_id.tl_office_percent')
    def _compute_tl_effective_bom_cost(self):
        for line in self:
            line.tl_has_budget_resources = bool(line.tl_resource_ids)
            line.tl_effective_bom_cost = line._tl_effective_budget_cost() if line.tl_resource_ids else 0.0

    def _tl_resource_line_ids(self):
        """Only use sudo to detect existence; all data are subsequently read as user."""
        rows = self.env['tl.construction.budget.resource'].sudo().search([('sale_line_id', 'in', self.ids)])
        return set(rows.mapped('sale_line_id').ids)

    def _tl_effective_budget_cost(self):
        self.ensure_one()
        resources = self.tl_resource_ids
        mismatched = resources.filtered(lambda r: r.source_bom_line_id and r.source_bom_line_id.bom_id != self.x_bom_id)
        if mismatched:
            raise UserError(_('Budget resources belong to a different bill of materials. Review them before updating costs.'))
        return self.tl_direct_unit_cost * (1 + self.order_id.tl_office_percent / 100.0)

    def _tl_apply_cost_preserving_price(self, cost):
        self.ensure_one()
        self.order_id.check_access('write')
        original = self.price_unit
        self.write({'purchase_price': cost})
        precision = max(6, self.env['decimal.precision'].precision_get('Product Price') or 2)
        if float_compare(self.price_unit, original, precision_digits=precision):
            raise UserError(_('The sales price changed while applying costs. The operation was stopped.'))


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    def _run_action_code_multi(self, eval_context):
        self.ensure_one()
        if self.model_id.model not in ('sale.order', 'sale.order.line'):
            return super()._run_action_code_multi(eval_context)
        apply_action = self.env.ref('construction_developer.action_update_sol_cost_price_margin_on_x_bom_id_write', raise_if_not_found=False)
        open_action = self.env.ref('construction_developer.action_view_sale_order_line_bom_list', raise_if_not_found=False)
        if self != apply_action and self != open_action:
            return super()._run_action_code_multi(eval_context)
        caller_env = eval_context['env']
        manager = caller_env.su or caller_env.user.has_group('sales_team.group_sale_manager')
        if self == apply_action:
            lines = eval_context.get('records') or eval_context.get('record')
            if not lines or lines._name != 'sale.order.line':
                return super()._run_action_code_multi(eval_context)
            lines = lines.exists()
            estimated_ids = lines._tl_resource_line_ids()
            if estimated_ids and not manager:
                raise UserError(_('A sales manager must update lines containing budget resources.'))
            protected = lines.filtered(lambda line: line.id in estimated_ids or (manager and line.x_bom_id and line.x_bom_id.x_original_sol_id == line))
            if not protected:
                return super()._run_action_code_multi(eval_context)
            if _normalized(self.code) != _normalized(_APPLY):
                raise UserError(_('The Construction Developer cost action has been modified. Review it before updating costs.'))
            standard = lines - protected
            result = False
            if standard:
                standard_context = dict(eval_context, records=standard, record=standard[:1])
                result = super()._run_action_code_multi(standard_context)
            for line in protected:
                line.order_id.check_access('write')
                # A confirmed quotation's approved costs and price are not
                # changed when an MO creates another quotation-specific BoM.
                if line.order_id.state not in ('draft', 'sent'):
                    continue
                if line.id in estimated_ids:
                    if line.product_uom_qty <= 0:
                        raise UserError(_('A budgeted sales line must have a positive quantity.'))
                    cost = line._tl_effective_budget_cost()
                else:
                    cost = line.x_bom_id.x_bom_cost
                line._tl_apply_cost_preserving_price(cost)
            return result
        order = eval_context.get('record') or eval_context.get('records')
        if not order or order._name != 'sale.order' or len(order) != 1:
            return super()._run_action_code_multi(eval_context)
        lines = order.order_line.filtered(lambda line: line.x_bom_id)
        estimated_ids = lines._tl_resource_line_ids()
        if estimated_ids and not manager:
            raise UserError(_('A sales manager must update lines containing budget resources.'))
        if not estimated_ids:
            return super()._run_action_code_multi(eval_context)
        if _normalized(self.code) != _normalized(_OPEN):
            raise UserError(_('The Construction Developer cost window action has been modified. Review it before updating costs.'))
        order.check_access('write')
        for line in lines:
            cost = line._tl_effective_budget_cost() if line.id in estimated_ids else line.x_bom_id.x_bom_cost
            line.write({'x_different_bom_cost': bool(fields.Float.compare(line.purchase_price, cost, precision_digits=max(6, caller_env['decimal.precision'].precision_get('Product Price') or 2)))})
        action = caller_env.ref('construction_developer.window_action_view_sale_order_line_bom_list').read()[0]
        action['domain'] = [('x_bom_id', '!=', False), ('id', 'in', order.order_line.ids)]
        return action
