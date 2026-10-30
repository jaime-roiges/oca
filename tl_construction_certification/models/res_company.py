# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    construction_approval_policy = fields.Selection(
        [
            ("open", "Sales users (legacy behaviour)"),
            ("restricted", "Sales managers or designated project approver"),
        ],
        string="Construction Certification Approval",
        default="open",
        required=True,
        help="Restricted approvals are checked server-side, including RPC, "
        "imports and automated writes. Existing companies stay on the "
        "legacy policy until their administrators enable restricted approval.",
    )
    construction_advance_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Construction Advance Account",
        domain="[('account_type', '=', 'liability_current'), ('company_ids', 'in', id)]",
        help="Liability credited when a customer advance is invoiced and "
        "debited when that advance is deducted on the origin invoice. "
        "It must belong to this company. It is marked reconcilable so the "
        "advance invoice and the deduction can be matched.",
    )
    construction_retention_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Construction Retention Account",
        domain="[('account_type', '=', 'asset_current'), ('company_ids', 'in', id)]",
        help="Asset debited when guarantee retention is withheld and "
        "credited when that retention is released. It must belong to this "
        "company and it is not an income account.",
    )

    @api.constrains("construction_advance_account_id", "construction_retention_account_id")
    def _check_construction_accounts_company(self):
        for company in self:
            accounts = company.construction_advance_account_id | company.construction_retention_account_id
            for account in accounts:
                if company not in account.company_ids:
                    raise ValidationError(
                        _("Account %s does not belong to company %s.")
                        % (account.display_name, company.display_name)
                    )
            if (
                company.construction_advance_account_id
                and company.construction_advance_account_id.account_type != "liability_current"
            ):
                raise ValidationError(_("The construction advance account must be a current liability."))
            if (
                company.construction_retention_account_id
                and company.construction_retention_account_id.account_type != "asset_current"
            ):
                raise ValidationError(_("The construction retention account must be a current asset."))

    def _prepare_construction_account(self, account, expected_type):
        self.ensure_one()
        if account.account_type != expected_type:
            raise UserError(_(
                "Account %(account)s must have the accounting type %(type)s."
            ) % {"account": account.display_name, "type": expected_type})
        if self not in account.company_ids:
            raise UserError(
                _("Account %s does not belong to company %s.")
                % (account.display_name, self.display_name)
            )
        if not account.reconcile:
            raise UserError(
                _("Account %s has to be reconcilable so the advance or the retention can be matched. "
                  "Mark it as reconcilable on the account, then invoice again.")
                % account.display_name
            )
        return account

    def _get_construction_advance_account(self):
        self.ensure_one()
        if not self.construction_advance_account_id:
            raise UserError(
                _("Set the construction advance account on company %s.")
                % self.display_name
            )
        return self._prepare_construction_account(self.construction_advance_account_id, "liability_current")

    def _get_construction_retention_account(self):
        self.ensure_one()
        if not self.construction_retention_account_id:
            raise UserError(
                _("Set the construction retention account on company %s.")
                % self.display_name
            )
        return self._prepare_construction_account(self.construction_retention_account_id, "asset_current")
