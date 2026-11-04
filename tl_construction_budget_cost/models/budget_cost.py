# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionBudgetResource(models.Model):
    _name = 'tl.construction.budget.resource'
    _description = 'Quotation work item resource estimate'
    _order = 'sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    source_bom_line_id = fields.Many2one('mrp.bom.line', string='Source BoM line', ondelete='set null', copy=True)
    sale_line_id = fields.Many2one('sale.order.line', required=True, ondelete='cascade', index=True, check_company=True)
    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', index=True, check_company=True, copy=False)
    company_id = fields.Many2one(related='order_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    product_id = fields.Many2one('product.product', string='Resource', required=True, check_company=True)
    name = fields.Char(string='Description', required=True)
    uom_id = fields.Many2one('uom.uom', string='Resource unit', required=True, help='Unit for the entered quantity and budgeted unit cost.')
    quantity = fields.Float(string='Quantity per sale unit', digits='Product Unit of Measure', required=True, default=1.0)
    unit_cost = fields.Float(string='Budgeted unit cost', digits='Product Price', required=True)
    amount_unit = fields.Float(string='Cost per sale unit', compute='_compute_amount_unit', store=True, digits='Product Price')
    category = fields.Selection([('material', 'Materials'), ('labor', 'Labour'), ('equipment', 'Equipment'), ('subcontract', 'Subcontracting'), ('other', 'Other direct costs')], default='material', required=True)

    @api.depends('quantity', 'unit_cost', 'currency_id')
    def _compute_amount_unit(self):
        for line in self:
            line.amount_unit = line.quantity * line.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.name = line.product_id.display_name
                line.uom_id = line.product_id.uom_id
                order = line.order_id
                product = line.product_id.with_company(order.company_id) if order.company_id else line.product_id
                cost = product.standard_price
                if order.company_id and order.currency_id:
                    cost = order.company_id.currency_id._convert(cost, order.currency_id, order.company_id, fields.Date.context_today(order))
                line.unit_cost = cost

    @api.constrains('quantity', 'unit_cost', 'sale_line_id')
    def _check_values(self):
        for line in self:
            if line.quantity < 0 or line.unit_cost < 0:
                raise ValidationError(_('Resource quantities and costs must not be negative.'))
            if line.sale_line_id.display_type or not line.sale_line_id.product_id:
                raise ValidationError(_('Choose a sales line with a product.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sale_line = self.env['sale.order.line'].browse(vals.get('sale_line_id')).exists()
            if not sale_line or sale_line.order_id.state not in ('draft', 'sent'):
                raise UserError(_('Resources can only be edited on a quotation.'))
            sale_line.order_id.check_access('write')
            if vals.get('order_id') and vals['order_id'] != sale_line.order_id.id:
                raise ValidationError(_('The selected sales line must belong to the quotation.'))
            vals['order_id'] = sale_line.order_id.id
            if not vals.get('uom_id') and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id']).exists()
                if product:
                    vals['uom_id'] = product.uom_id.id
        return super().create(vals_list)

    def write(self, vals):
        if self.filtered(lambda line: line.order_id.state not in ('draft', 'sent')):
            raise UserError(_('Resources can only be edited on a quotation.'))
        self.mapped('order_id').check_access('write')
        if 'order_id' in vals and any(vals['order_id'] != line.order_id.id for line in self):
            raise ValidationError(_('Resources cannot be moved to another quotation.'))
        if 'sale_line_id' in vals:
            new_line = self.env['sale.order.line'].browse(vals['sale_line_id']).exists()
            if not new_line or new_line.order_id.state not in ('draft', 'sent'):
                raise UserError(_('Resources can only be edited on a quotation.'))
            new_line.order_id.check_access('write')
            if any(line.order_id != new_line.order_id for line in self):
                raise ValidationError(_('The selected sales line must belong to the quotation.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.order_id.state not in ('draft', 'sent')):
            raise UserError(_('Resources can only be edited on a quotation.'))
        self.mapped('order_id').check_access('write')
        return super().unlink()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    tl_resource_ids = fields.One2many('tl.construction.budget.resource', 'sale_line_id', string='Budget resources', copy=True, groups='sales_team.group_sale_manager')
    tl_direct_unit_cost = fields.Float(string='Budgeted direct cost per unit', compute='_compute_tl_direct_unit_cost', digits='Product Price', groups='sales_team.group_sale_manager')

    @api.depends('tl_resource_ids.amount_unit')
    def _compute_tl_direct_unit_cost(self):
        for line in self:
            line.tl_direct_unit_cost = sum(line.tl_resource_ids.mapped('amount_unit'))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tl_office_percent = fields.Float(string='Office overhead (%)', digits=(16, 2), copy=True, groups='sales_team.group_sale_manager')
    tl_resource_ids = fields.One2many('tl.construction.budget.resource', 'order_id', string='Budget resources', groups='sales_team.group_sale_manager')
    tl_direct_cost = fields.Monetary(string='Direct budgeted cost', compute='_compute_tl_cost_totals', currency_field='currency_id', groups='sales_team.group_sale_manager')
    tl_office_cost = fields.Monetary(string='Budgeted office overhead', compute='_compute_tl_cost_totals', currency_field='currency_id', groups='sales_team.group_sale_manager')
    tl_budget_total = fields.Monetary(string='Total budgeted cost', compute='_compute_tl_cost_totals', currency_field='currency_id', groups='sales_team.group_sale_manager')
    tl_unestimated_count = fields.Integer(string='Sales lines without resources', compute='_compute_tl_cost_totals', groups='sales_team.group_sale_manager')
    tl_budget_margin = fields.Monetary(string='Estimated margin', compute='_compute_tl_cost_totals', currency_field='currency_id', groups='sales_team.group_sale_manager')
    tl_snapshot_direct = fields.Monetary(string='Approved direct cost', readonly=True, copy=False, currency_field='currency_id', groups='sales_team.group_sale_manager')
    tl_snapshot_office = fields.Monetary(string='Approved office overhead', readonly=True, copy=False, currency_field='currency_id', groups='sales_team.group_sale_manager')
    tl_snapshot_recorded = fields.Boolean(string='Cost snapshot recorded', readonly=True, copy=False, groups='sales_team.group_sale_manager')

    @api.depends('order_line.tl_direct_unit_cost', 'order_line.product_uom_qty', 'tl_office_percent', 'amount_untaxed', 'currency_id')
    def _compute_tl_cost_totals(self):
        for order in self:
            direct = sum(line.tl_direct_unit_cost * max(line.product_uom_qty, 0.0) for line in order.order_line)
            overhead = direct * order.tl_office_percent / 100.0
            order.tl_unestimated_count = len(order.order_line.filtered(lambda line: not line.display_type and line.product_id and line.product_uom_qty > 0 and not line.tl_resource_ids))
            order.tl_direct_cost = direct
            order.tl_office_cost = overhead
            order.tl_budget_total = direct + overhead
            order.tl_budget_margin = order.amount_untaxed - direct - overhead

    @api.constrains('tl_office_percent')
    def _check_tl_office_percent(self):
        if any(order.tl_office_percent < 0 or order.tl_office_percent > 100 for order in self):
            raise ValidationError(_('Office overhead must be between 0 and 100 percent.'))

    def write(self, vals):
        if 'tl_office_percent' in vals and self.filtered(lambda order: order.state not in ('draft', 'sent')):
            raise UserError(_('Office overhead can only be changed on a quotation.'))
        return super().write(vals)

    def action_tl_import_bom_resources(self):
        self.ensure_one()
        self.check_access('write')
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Resources can only be edited on a quotation.'))
        candidates = self.order_line.filtered(lambda line: not line.display_type and line.product_id and line.product_uom_qty > 0 and line.x_bom_id and not line.tl_resource_ids)
        if not candidates:
            raise UserError(_('No sales lines with an available bill of materials and an empty resource list were found.'))
        vals_list = []
        for sale_line in candidates:
            bom = sale_line.x_bom_id
            if not bom.product_qty or bom.uom_id != sale_line.product_uom_id:
                raise UserError(_('The bill of materials and sales line must use the same unit and the BoM quantity must be positive.'))
            if bom.operation_ids:
                raise UserError(_('A bill of materials contains operations. Enter its resource costs manually to avoid omitting operations.'))
            if not bom.bom_line_ids:
                raise UserError(_('A bill of materials has no components.'))
            for component in bom.bom_line_ids:
                product = component.product_id.with_company(self.company_id)
                if 'uom_id' in component._fields:
                    unit = component.uom_id
                elif 'product_uom_id' in component._fields:
                    unit = component.product_uom_id
                else:
                    raise UserError(_('Cannot determine the unit of a BoM component.'))
                if unit != product.uom_id:
                    raise UserError(_('A BoM component uses a different unit than its product. Enter it manually.'))
                cost = self.company_id.currency_id._convert(product.standard_price, self.currency_id, self.company_id, fields.Date.context_today(self))
                vals_list.append({'sale_line_id': sale_line.id, 'source_bom_line_id': component.id, 'product_id': product.id, 'uom_id': unit.id, 'name': product.display_name, 'quantity': component.product_qty / bom.product_qty, 'unit_cost': cost})
        self.env['tl.construction.budget.resource'].create(vals_list)
        return True

    def action_tl_apply_budget_costs(self):
        self.ensure_one()
        self.check_access('write')
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Costs can only be applied on a quotation.'))
        lines = self.order_line.filtered(lambda line: line.tl_resource_ids and line.product_uom_qty > 0 and not line.display_type)
        if not lines:
            raise UserError(_('Add at least one resource to a positive sales line.'))
        for line in lines:
            old_price = line.price_unit
            line.write({'purchase_price': line.tl_direct_unit_cost * (1 + self.tl_office_percent / 100.0)})
            if self.currency_id.compare_amounts(line.price_unit, old_price):
                raise UserError(_('The sales price changed while applying costs. The operation was stopped.'))
        return True

    def action_confirm(self):
        # Snapshot budget costs as an internal management estimate, not stock valuation.
        is_manager = self.env.su or self.env.user.has_group('sales_team.group_sale_manager')
        for order in self:
            has_resources = self.env['tl.construction.budget.resource'].sudo().search_count([('order_id', '=', order.id)], limit=1)
            if has_resources:
                if not is_manager:
                    raise UserError(_('A sales manager must confirm quotations containing budget resources.'))
                order.write({'tl_snapshot_direct': order.tl_direct_cost, 'tl_snapshot_office': order.tl_office_cost, 'tl_snapshot_recorded': True})
        return super().action_confirm()
