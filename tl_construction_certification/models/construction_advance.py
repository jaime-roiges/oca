# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionAdvance(models.Model):
    _name = "construction.advance"
    _description = "Construction Advance (Anticipo de Obra)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        required=True,
        tracking=True,
        check_company=True,
        index=True,
    )
    partner_id = fields.Many2one(
        related="sale_order_id.partner_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="sale_order_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        store=True,
    )
    tax_ids = fields.Many2many(
        comodel_name="account.tax",
        relation="construction_advance_tax_rel",
        column1="advance_id",
        column2="tax_id",
        string="Taxes",
        domain="[('type_tax_use', '=', 'sale')]",
        check_company=True,
        help="VAT on the advance. The amount is the tax-excluded base. "
        "The same taxes are reversed when the advance is deducted on the origin invoice.",
    )
    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
    )
    amount = fields.Monetary(
        string="Advance Amount",
        required=True,
        currency_field="currency_id",
    )
    application_ids = fields.One2many(
        comodel_name="construction.advance.application",
        inverse_name="advance_id",
        string="Applications",
    )
    amount_applied = fields.Monetary(
        string="Amount Applied",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_pending = fields.Monetary(
        string="Pending Amount",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("applied", "Fully Applied"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        copy=False,
    )
    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Advance Invoice",
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string="Notes")

    @api.model
    def _default_taxes(self, sale_order):
        """Taxes shared by the budget, otherwise the company sale tax."""
        lines = sale_order.order_line.filtered(lambda line: not line.display_type and line.product_id)
        if not lines:
            return self.env["account.tax"]
        first = lines[0].tax_ids
        if all(line.tax_ids == first for line in lines):
            return first
        return sale_order.company_id.account_sale_tax_id

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if self.sale_order_id and not self.tax_ids:
            self.tax_ids = self._default_taxes(self.sale_order_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") != "draft" or vals.get("invoice_id"):
                raise UserError(_("New advances must start as draft without an invoice."))
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "construction.advance"
                ) or _("New")
            if "tax_ids" not in vals and vals.get("sale_order_id"):
                order = self.env["sale.order"].browse(vals["sale_order_id"])
                taxes = self._default_taxes(order)
                if taxes:
                    vals["tax_ids"] = [(6, 0, taxes.ids)]
        return super().create(vals_list)

    def write(self, vals):
        economic = {"sale_order_id", "date", "amount", "tax_ids"}
        if economic.intersection(vals) and any(advance.state != "draft" for advance in self):
            raise UserError(_(
                "Confirmed, applied or cancelled advances cannot be edited. "
                "Use an accounting adjustment or create a new advance."
            ))
        if "invoice_id" in vals:
            invoice = self.env["account.move"].browse(vals["invoice_id"]) if vals["invoice_id"] else False
            for advance in self:
                if advance.invoice_id and advance.invoice_id != invoice:
                    raise UserError(_("The advance's linked invoice cannot be replaced or removed."))
                if invoice and (
                    invoice.move_type != "out_invoice"
                    or invoice.company_id != advance.company_id
                    or invoice.partner_id != (
                        advance.sale_order_id.partner_invoice_id or advance.partner_id
                    )
                ):
                    raise UserError(_("The advance invoice must belong to the same company and billing customer."))
            if invoice and not self.env.user.has_group("account.group_account_invoice"):
                raise UserError(_("Only billing users can attach an advance invoice."))
        if "state" in vals:
            for advance in self:
                new_state = vals["state"]
                if new_state == advance.state:
                    continue
                allowed = {
                    "draft": ("confirmed", "cancel"),
                    "confirmed": ("applied", "cancel"),
                    "applied": ("confirmed", "cancel"),
                    "cancel": ("draft", "confirmed"),
                }
                if new_state not in allowed.get(advance.state, ()):
                    raise UserError(_("Invalid advance state transition."))
                if new_state == "applied" and advance.currency_id.compare_amounts(advance.amount_pending, 0.0) > 0:
                    raise UserError(_("An advance with a pending balance cannot be fully applied."))
                if (
                    new_state == "confirmed" and advance.state == "applied"
                    and advance.currency_id.compare_amounts(advance.amount_pending, 0.0) <= 0
                ):
                    raise UserError(_("A fully applied advance cannot be marked pending."))
                if new_state == "confirmed" and advance.state == "cancel":
                    if (
                        not advance.invoice_id
                        or advance.invoice_id.state != "posted"
                        or advance.invoice_id._construction_reversal_is_complete(advance.invoice_id)
                    ):
                        raise UserError(_(
                            "The advance may be restored only after its posted credit "
                            "note is reversed."
                        ))
                if new_state == "confirmed" and advance.currency_id.compare_amounts(advance.amount, 0.0) <= 0:
                    raise UserError(_("Advance amount must be strictly positive."))
                if new_state == "cancel":
                    active = advance.application_ids.filtered(
                        lambda app: app.certification_id.state != "cancel"
                    )
                    if active:
                        raise UserError(_("Cannot cancel an advance applied on active certifications."))
                    invoice = advance.invoice_id
                    if invoice and invoice.state == "draft":
                        raise UserError(_("Cancel the draft advance invoice first."))
                    if (
                        invoice and invoice.state == "posted"
                        and not invoice._construction_reversal_is_complete(invoice)
                    ):
                        raise UserError(_("The advance invoice must be fully reversed before cancellation."))
                if new_state == "draft" and advance.invoice_id and advance.invoice_id.state == "posted":
                    raise UserError(_("An advance with a posted invoice cannot return to draft."))
        return super().write(vals)

    @api.depends(
        "amount",
        "application_ids.amount",
        "application_ids.certification_id.state",
    )
    def _compute_amounts(self):
        for advance in self:
            applied = sum(
                advance.application_ids.filtered(
                    lambda app: app.certification_id.state != "cancel"
                ).mapped("amount")
            )
            credited = advance._credited_deduction()
            currency = advance.currency_id
            if currency:
                applied = currency.round(applied)
                credited = currency.round(credited)
                pending = currency.round(advance.amount - applied + credited)
            else:
                pending = advance.amount - applied + credited
            advance.amount_applied = max(applied - credited, 0.0)
            advance.amount_pending = pending

    def _credited_deduction(self, applications=None):
        """Advance deduction returned by a posted credit note.

        The application row stays. The money was given back, so the pending
        balance has to come back too, unless that credit note was reversed.
        """
        self.ensure_one()
        if applications is None:
            applications = self.application_ids.filtered(
                lambda app: app.certification_id.state != "cancel"
            )
        if not applications:
            return 0.0
        lines = self.env["account.move.line"].search([
            ("construction_advance_application_id", "in", applications.ids),
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_refund", "in_refund")),
            ("move_id.reversed_entry_id.move_type", "in", ("out_invoice", "in_invoice")),
        ])
        lines = self.env["construction.certification.line"]._without_reversed_credits(lines)
        return sum(abs(line.price_subtotal or 0.0) for line in lines)

    @api.constrains("amount")
    def _check_amount(self):
        for advance in self:
            if advance.currency_id.compare_amounts(advance.amount, 0.0) <= 0:
                raise ValidationError(_("Advance amount must be strictly positive."))

    def _refresh_applied_state(self):
        for advance in self:
            if advance.state not in ("confirmed", "applied"):
                continue
            pending = advance.amount_pending
            if advance.currency_id.compare_amounts(pending, 0.0) <= 0:
                if advance.state != "applied":
                    advance.state = "applied"
            elif advance.state == "applied":
                advance.state = "confirmed"

    def _taxes_charged(self):
        """Taxes on the posted advance invoice.

        Empty when that invoice is not posted. Callers that are about to
        deduct the advance must reject this case first: a compute must not
        raise, or opening the invoice later becomes impossible.
        """
        self.ensure_one()
        invoice = self.invoice_id
        if not invoice or invoice.state != "posted":
            return self.env["account.tax"]
        source = invoice.line_ids.filtered(lambda line: line.construction_advance_id == self)[:1]
        return source.tax_ids

    def action_confirm(self):
        for advance in self:
            if advance.state != "draft":
                raise UserError(_("Only draft advances can be confirmed."))
            if advance.currency_id.compare_amounts(advance.amount, 0.0) <= 0:
                raise UserError(_("Advance amount must be strictly positive."))
        self.write({"state": "confirmed"})

    def action_cancel(self):
        for advance in self:
            active_apps = advance.application_ids.filtered(
                lambda app: app.certification_id.state != "cancel"
            )
            if active_apps:
                raise UserError(
                    _("Cannot cancel advance %s because it is applied on certifications.")
                    % advance.display_name
                )
        invoiced = self.filtered(lambda advance: advance.invoice_id and advance.invoice_id.state != "cancel")
        if invoiced and not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("Only billing users can cancel an advance that has an invoice."))
        for advance in self:
            advance.invoice_id._construction_cancel_or_reverse()
        self.filtered(lambda advance: advance.state != "cancel").write({"state": "cancel"})

    def action_create_invoice(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Only confirmed advances can be invoiced."))
        if self.invoice_id and self.invoice_id.state != "cancel":
            raise UserError(_("This advance already has an invoice."))
        if not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("Only billing users can invoice an advance."))
        order = self.sale_order_id
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": (order.partner_invoice_id or self.partner_id).id,
            "partner_shipping_id": order.partner_shipping_id.id,
            "fiscal_position_id": order.fiscal_position_id.id,
            "invoice_payment_term_id": order.payment_term_id.id,
            "document_tax_mode": "tax_excluded",
            "invoice_origin": self.name,
            "invoice_date": self.date,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "narration": _("Advance payment for construction works - %s") % self.name,
            "invoice_line_ids": [(0, 0, self._prepare_invoice_line_vals())],
        })
        self.invoice_id = invoice.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
        }

    def _prepare_invoice_line_vals(self):
        self.ensure_one()
        vals = {
            "name": _("Advance - %s") % self.name,
            "quantity": 1.0,
            "price_unit": self.amount,
            "account_id": self.company_id._get_construction_advance_account().id,
            "tax_ids": [(6, 0, self.tax_ids.ids)],
            "construction_advance_id": self.id,
            "construction_adjustment_type": "advance_invoice",
            **self._advance_analytic_vals(),
        }
        return vals

    def _advance_analytic_distribution(self):
        """Sale-line or project analytic, so the advance is visible on the job."""
        self.ensure_one()
        if "analytic_distribution" not in self.env["account.move.line"]._fields:
            return False
        order = self.sale_order_id
        for line in order.order_line.filtered(lambda item: not item.display_type):
            if "analytic_distribution" in line._fields and line.analytic_distribution:
                return line.analytic_distribution
        project = order.project_id
        analytic = project.account_id if project and "account_id" in project._fields else False
        if analytic and analytic._name == "account.analytic.account":
            return {str(analytic.id): 100.0}
        return False

    def _advance_analytic_vals(self):
        distribution = self._advance_analytic_distribution()
        if distribution:
            return {"analytic_distribution": distribution}
        return {}

    def unlink(self):
        for advance in self:
            if advance.state != "draft" or advance.application_ids or advance.invoice_id:
                raise UserError(_(
                    "Only draft advances without applications or an invoice history can be deleted."
                ))
        return super().unlink()


class ConstructionAdvanceApplication(models.Model):
    _name = "construction.advance.application"
    _description = "Advance Application on a Work Certification"
    _order = "id"
    _check_company_auto = True

    advance_id = fields.Many2one(
        comodel_name="construction.advance",
        string="Advance",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    certification_id = fields.Many2one(
        comodel_name="construction.certification",
        string="Certification",
        required=True,
        ondelete="cascade",
        index=True,
    )
    currency_id = fields.Many2one(
        related="advance_id.currency_id",
        store=True,
    )
    company_id = fields.Many2one(
        related="advance_id.company_id",
        store=True,
    )
    amount = fields.Monetary(
        string="Amount",
        required=True,
        currency_field="currency_id",
    )
    certification_state = fields.Selection(
        related="certification_id.state",
        string="Certification Status",
    )
    invoice_id = fields.Many2one(
        related="certification_id.invoice_id",
        string="Origin Invoice",
    )
    invoice_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="construction_advance_application_id",
        string="Invoice Lines",
        help="Origin-invoice lines that deduct this application.",
    )

    _advance_certification_uniq = models.Constraint(
        "UNIQUE(advance_id, certification_id)",
        "An advance can be applied only once on the same certification.",
    )

    @api.constrains("amount", "advance_id", "certification_id")
    def _check_amount(self):
        for app in self:
            if app.currency_id.compare_amounts(app.amount, 0.0) <= 0:
                raise ValidationError(_("Applied advance amount must be strictly positive."))
            if app.advance_id.sale_order_id != app.certification_id.sale_order_id:
                raise ValidationError(
                    _("Advance %s does not belong to the certification sales order.")
                    % app.advance_id.display_name
                )
            if app.advance_id.state not in ("confirmed", "applied"):
                raise ValidationError(
                    _("Advance %s must be confirmed before it can be applied.")
                    % app.advance_id.display_name
                )
            pending_others = app.advance_id.amount - sum(
                app.advance_id.application_ids.filtered(
                    lambda other: other.id != app.id and other.certification_id.state != "cancel"
                ).mapped("amount")
            )
            pending_others += app.advance_id._credited_deduction(
                app.advance_id.application_ids.filtered(
                    lambda other: other.id != app.id and other.certification_id.state != "cancel"
                )
            )
            if app.currency_id.compare_amounts(app.amount, pending_others) > 0:
                raise ValidationError(
                    _("Applied amount exceeds the pending balance of advance %s.")
                    % app.advance_id.display_name
                )

    def _check_certification_editable(self):
        locked = self.filtered(lambda app: app.certification_id.state not in ("draft", "measured"))
        if locked:
            raise UserError(
                _("Advance applications can only be changed while the certification is draft or measured.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_certification_editable()
        records.mapped("advance_id")._refresh_applied_state()
        return records

    def write(self, vals):
        self._check_certification_editable()
        advances = self.mapped("advance_id")
        res = super().write(vals)
        (advances | self.mapped("advance_id"))._refresh_applied_state()
        return res

    def unlink(self):
        self._check_certification_editable()
        advances = self.mapped("advance_id")
        res = super().unlink()
        advances._refresh_applied_state()
        return res
