from odoo import _, fields, models
from odoo.exceptions import UserError


class AdvanceApplyWizard(models.TransientModel):
    _name = 'tl.dimpal.advance.apply.wizard'
    _description = 'Apply Fiscal Advance to Partial Invoice'

    invoice_id = fields.Many2one('account.move', required=True)
    advance_id = fields.Many2one('tl.dimpal.advance', required=True)
    amount_base = fields.Monetary(required=True)
    currency_id = fields.Many2one('res.currency', related='invoice_id.currency_id')

    def action_apply(self):
        self.ensure_one()
        invoice = self.invoice_id
        invoice.check_access('write')
        if not self.env.user.has_group('account.group_account_user'):
            raise UserError(_('Accounting access is required.'))
        self.advance_id._dimpal_allocate_to(invoice, self.amount_base)
        return {'type': 'ir.actions.act_window', 'name': _('Invoice with applied advance'),
                'res_model': 'account.move', 'res_id': invoice.id, 'view_mode': 'form'}
