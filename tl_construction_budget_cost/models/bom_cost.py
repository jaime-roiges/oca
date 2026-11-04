# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    tl_budget_editable = fields.Boolean(compute='_compute_tl_budget_editable', groups='sales_team.group_sale_manager')

    @api.depends('product_qty')
    def _compute_tl_budget_editable(self):
        for bom in self:
            sale_line = bom.x_original_sol_id
            bom.tl_budget_editable = bool(sale_line and sale_line.order_id.state in ('draft', 'sent') and sale_line.x_bom_id == bom)

    def _tl_get_quotation_line(self):
        self.ensure_one()
        line = self.x_original_sol_id
        if not line or line.x_bom_id != self or line.order_id.state not in ('draft', 'sent'):
            raise UserError(_('Open the quotation-specific bill of materials from a draft sales order.'))
        line.order_id.check_access('write')
        if not self.product_qty or self.uom_id != line.product_uom_id:
            raise UserError(_('The bill of materials and sales line must use the same unit and the BoM quantity must be positive.'))
        if self.operation_ids:
            raise UserError(_('A bill of materials contains operations. Enter its resource costs manually to avoid omitting operations.'))
        return line

    def action_tl_prepare_bom_costs(self):
        if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_('Only a sales manager can edit quotation costs.'))
        for bom in self:
            bom._tl_sync_quote_resources()
        return True

    def _tl_sync_quote_resources(self, overrides=None):
        self.ensure_one()
        line = self._tl_get_quotation_line()
        order = line.order_id
        overrides = overrides or {}
        if not self.bom_line_ids:
            raise UserError(_('A bill of materials has no components.'))
        # Serialize concurrent initialization for the same quotation line.
        self.env.cr.execute('SELECT id FROM sale_order_line WHERE id = %s FOR UPDATE', [line.id])
        line.invalidate_recordset(['tl_resource_ids'])
        resources = line.tl_resource_ids
        if resources.filtered(lambda r: not r.source_bom_line_id or r.source_bom_line_id.bom_id != self):
            raise UserError(_('This sales line already has manual or unrelated resources. Reconcile them in the budget tab before preparing the bill of materials.'))
        for component in self.bom_line_ids:
            product = component.product_id.with_company(order.company_id)
            unit = component.uom_id
            if not product or unit != product.uom_id:
                raise UserError(_('A BoM component uses a different unit than its product. Enter it manually.'))
            matches = resources.filtered(lambda r: r.source_bom_line_id == component)
            if len(matches) > 1:
                raise UserError(_('More than one budget resource refers to the same BoM component.'))
            vals = {'quantity': component.product_qty / self.product_qty, 'product_id': product.id, 'uom_id': unit.id}
            if component.id in overrides:
                vals['unit_cost'] = overrides[component.id]
            if matches:
                matches.write(vals)
            else:
                cost = order.company_id.currency_id._convert(product.standard_price, order.currency_id, order.company_id, fields.Date.context_today(order))
                vals.update({'sale_line_id': line.id, 'source_bom_line_id': component.id, 'name': product.display_name, 'unit_cost': overrides.get(component.id, cost)})
                self.env['tl.construction.budget.resource'].create(vals)
        return True

    def write(self, vals):
        res = super().write(vals)
        if 'product_qty' in vals:
            for bom in self:
                line = bom.x_original_sol_id
                if line and line.x_bom_id == bom and self.env['tl.construction.budget.resource'].sudo().search_count([('sale_line_id', '=', line.id), ('source_bom_line_id.bom_id', '=', bom.id)], limit=1):
                    if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
                        raise UserError(_('Only a sales manager can edit quotation costs.'))
                    bom._tl_sync_quote_resources()
        return res


class MrpBomLine(models.Model):
    _inherit = 'mrp.bom.line'

    tl_budget_unit_cost = fields.Float(string='Coste unitario presupuestado', digits=(16, 6), compute='_compute_tl_budget_unit_cost', inverse='_inverse_tl_budget_unit_cost', groups='sales_team.group_sale_manager')

    @api.depends('bom_id', 'product_id', 'uom_id')
    def _compute_tl_budget_unit_cost(self):
        Resource = self.env['tl.construction.budget.resource']
        for component in self:
            bom = component.bom_id
            line = bom.x_original_sol_id
            resource = Resource.search([('sale_line_id', '=', line.id), ('source_bom_line_id', '=', component.id)], limit=2) if line and component.id else Resource
            if len(resource) == 1:
                component.tl_budget_unit_cost = resource.unit_cost
            elif component.product_id and line:
                company = line.order_id.company_id
                cost = component.product_id.with_company(company).standard_price
                component.tl_budget_unit_cost = company.currency_id._convert(cost, line.order_id.currency_id, company, fields.Date.context_today(line.order_id))
            else:
                component.tl_budget_unit_cost = 0.0

    def _inverse_tl_budget_unit_cost(self):
        for component in self:
            if component.tl_budget_unit_cost < 0:
                raise UserError(_('Resource quantities and costs must not be negative.'))
            component.bom_id._tl_sync_quote_resources({component.id: component.tl_budget_unit_cost})

    def write(self, vals):
        changed_identity = any(('product_id' in vals and component.product_id.id != vals['product_id']) or ('uom_id' in vals and component.uom_id.id != vals['uom_id']) for component in self)
        if changed_identity:
            linked = self.env['tl.construction.budget.resource'].sudo().search_count([('source_bom_line_id', 'in', self.ids)], limit=1)
            if linked:
                raise UserError(_('A budgeted component cannot change product or unit. Remove its budget resource first.'))
        result = super().write(vals)
        if 'product_qty' in vals:
            boms = self.mapped('bom_id')
            for bom in boms:
                line = bom.x_original_sol_id
                if line and line.x_bom_id == bom and self.env['tl.construction.budget.resource'].sudo().search_count([('sale_line_id', '=', line.id), ('source_bom_line_id.bom_id', '=', bom.id)], limit=1):
                    if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
                        raise UserError(_('Only a sales manager can edit quotation costs.'))
                    bom._tl_sync_quote_resources()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for bom in records.mapped('bom_id'):
            line = bom.x_original_sol_id
            if line and line.x_bom_id == bom and self.env['tl.construction.budget.resource'].sudo().search_count([('sale_line_id', '=', line.id), ('source_bom_line_id.bom_id', '=', bom.id)], limit=1):
                if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
                    raise UserError(_('Only a sales manager can edit quotation costs.'))
                bom._tl_sync_quote_resources()
        return records

    def unlink(self):
        linked = self.env['tl.construction.budget.resource'].sudo().search_count([('source_bom_line_id', 'in', self.ids)], limit=1)
        if linked:
            if not self.env.su and not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_('Only a sales manager can edit quotation costs.'))
            self.env['tl.construction.budget.resource'].search([('source_bom_line_id', 'in', self.ids)]).unlink()
        return super().unlink()
