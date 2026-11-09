from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvanceRegisterWizard(models.TransientModel):
    _name = 'tl.dimpal.advance.register.wizard'
    _description = 'Register an Existing Fiscal Advance Invoice'

    invoice_id = fields.Many2one('account.move', required=True)
    invoice_line_id = fields.Many2one('account.move.line', required=True,
                                      domain="[('move_id', '=', invoice_id)]")

    def action_register(self):
        self.ensure_one()
        move = self.invoice_id
        if not self.env.user.has_group('account.group_account_user'):
            raise UserError(_('Accounting access is required.'))
        blanket = move.dimpal_blanket_order_id
        if not blanket or blanket.order_type != 'blanket' or move.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(_('Invoice must be linked to a blanket sales order.'))
        if self.env['tl.dimpal.advance'].search_count([('invoice_line_id', '=', self.invoice_line_id.id)]):
            raise UserError(_('This advance line has already been registered.'))
        rec = self.env['tl.dimpal.advance'].create({
            'blanket_order_id': blanket.id,
            'kind': 'customer' if move.move_type == 'out_invoice' else 'supplier',
            'invoice_id': move.id, 'invoice_line_id': self.invoice_line_id.id,
        })
        return rec.action_view_invoice()
