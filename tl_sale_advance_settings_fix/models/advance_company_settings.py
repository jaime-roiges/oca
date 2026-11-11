from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class AdvanceCompanySettings(models.TransientModel):
    _name = "tl.advance.company.settings"
    _description = "Advance accounting settings by company"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    tl_customer_advance_account_id = fields.Many2one(
        "account.account",
        string="Customer advances (438)",
    )
    tl_supplier_advance_account_id = fields.Many2one(
        "account.account",
        string="Supplier advances (407)",
    )
    tl_auto_allocate_sales = fields.Boolean(
        string="Automatically allocate advances to customer invoices",
    )

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        company_id = result.get("company_id") or self.env.company.id
        # The old settings action may carry a false default_company_id.
        # Never allow that context to leave the company unset.
        result["company_id"] = company_id
        company = self.env["res.company"].browse(company_id)
        for field_name in (
            "tl_customer_advance_account_id",
            "tl_supplier_advance_account_id",
        ):
            if field_name in fields_list:
                result[field_name] = company[field_name].id or False
        if "tl_auto_allocate_sales" in fields_list:
            result["tl_auto_allocate_sales"] = company.tl_auto_allocate_sales
        return result

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if not self.company_id:
            self.tl_customer_advance_account_id = False
            self.tl_supplier_advance_account_id = False
            self.tl_auto_allocate_sales = False
            return
        self.tl_customer_advance_account_id = (
            self.company_id.tl_customer_advance_account_id
        )
        self.tl_supplier_advance_account_id = (
            self.company_id.tl_supplier_advance_account_id
        )
        self.tl_auto_allocate_sales = self.company_id.tl_auto_allocate_sales

    def _validate_account(self, account, allowed_types, prefix):
        self.ensure_one()
        if not account:
            return
        if account.account_type not in allowed_types:
            raise ValidationError(
                _("The selected %(prefix)s advance account has an invalid type.")
                % {"prefix": prefix}
            )
        # Odoo 20 account.account may be shared among companies: company_ids
        # is the authority for membership and code is company-dependent.
        if self.company_id not in account.company_ids:
            raise ValidationError(
                _("The %(prefix)s advance account is not available for %(company)s.")
                % {"prefix": prefix, "company": self.company_id.display_name}
            )
        code = account.with_company(self.company_id).code or ""
        if not code.startswith(prefix):
            raise ValidationError(
                _("The selected account must start with %(prefix)s for %(company)s.")
                % {"prefix": prefix, "company": self.company_id.display_name}
            )

    def action_save(self):
        self.ensure_one()
        if not (
            self.env.user.has_group("account.group_account_manager")
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError(_("Accounting manager access is required."))
        if self.company_id not in self.env.user.company_ids:
            raise AccessError(_("The selected company is not allowed for this user."))
        self._validate_account(
            self.tl_customer_advance_account_id,
            ("liability_current",),
            "438",
        )
        self._validate_account(
            self.tl_supplier_advance_account_id,
            ("asset_current", "asset_prepayments"),
            "407",
        )
        company = self.company_id.with_company(self.company_id)
        company.sudo().write(
            {
                "tl_customer_advance_account_id": (
                    self.tl_customer_advance_account_id.id or False
                ),
                "tl_supplier_advance_account_id": (
                    self.tl_supplier_advance_account_id.id or False
                ),
                "tl_auto_allocate_sales": self.tl_auto_allocate_sales,
            }
        )
        # Read back persistent values so an incomplete related/inverse
        # implementation cannot masquerade as a successful write.
        company.invalidate_recordset(
            [
                "tl_customer_advance_account_id",
                "tl_supplier_advance_account_id",
                "tl_auto_allocate_sales",
            ]
        )
        if (
            company.tl_customer_advance_account_id
            != self.tl_customer_advance_account_id
            or company.tl_supplier_advance_account_id
            != self.tl_supplier_advance_account_id
            or company.tl_auto_allocate_sales != self.tl_auto_allocate_sales
        ):
            raise ValidationError(
                _("The advance accounting settings could not be persisted.")
            )
        return {"type": "ir.actions.client", "tag": "reload"}
