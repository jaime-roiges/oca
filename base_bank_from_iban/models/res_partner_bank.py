# Copyright 2017 Tecnativa - Carlos Dauden
# Copyright 2024 Tecnativa - Pedro M. Baeza
# Copyright 2026 Migration to Odoo 20
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3).

import schwifty

from odoo import api, fields, models
from odoo.tools.bank_account_number import format_account_number


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    bank_code = fields.Char(
        string="Bank Code",
        help="Bank/institution code extracted from the IBAN when available.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._add_bank_vals_from_iban(dict(vals)) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._add_bank_vals_from_iban(vals)
        return super().write(vals)

    @api.model
    def _add_bank_vals_from_iban(self, vals):
        account_number = vals.get("account_number")
        if not account_number:
            return vals

        iban_vals = self._get_bank_vals_from_iban(account_number)
        # Preserve explicitly supplied values. The addon only enriches missing data.
        for field_name, value in iban_vals.items():
            if value and not vals.get(field_name):
                vals[field_name] = value
        return vals

    @api.model
    def _get_bank_vals_from_iban(self, account_number):
        """Return bank metadata for *account_number* without creating another model.

        Odoo 20 removed ``res.bank`` and stores bank metadata directly on
        ``res.partner.bank``.  Schwifty is therefore used only as a lookup source.
        """
        try:
            iban = schwifty.IBAN(account_number)
            bank = iban.bank
            if not bank:
                return {}
        except (
            schwifty.exceptions.InvalidStructure,
            schwifty.exceptions.InvalidChecksumDigits,
            ValueError,
        ):
            return {}

        country = self.env["res.country"].search(
            [("code", "=", iban.country_code)], limit=1
        )
        return {
            "bank_name": bank.get("name"),
            "bank_bic": bank.get("bic"),
            "bank_code": bank.get("bank_code"),
            "country_id": country.id,
        }

    @api.onchange("account_number")
    def _onchange_account_number_base_bank_from_iban(self):
        for account in self:
            if not account.account_number:
                continue
            formatted = format_account_number(account.env, account.account_number)
            account.account_number = formatted
            if account.retrieve_account_type(formatted) != "iban":
                continue
            vals = account._get_bank_vals_from_iban(formatted)
            for field_name, value in vals.items():
                if value:
                    account[field_name] = value
