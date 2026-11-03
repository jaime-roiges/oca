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
    collection_payment_id = fields.Many2one(
        "account.payment", string="Received payment", check_company=True,
        ondelete="restrict", copy=False,
        help="One recorded customer payment per advance. For partial receipts, "
             "create one advance per payment. Match the payment to the advance "
             "invoice using Odoo's standard reconciliation.",
    )
    collection_date = fields.Date(
        string="Actual receipt date", copy=False,
        help="Date the customer payment was actually received. This is not "
             "automatically inferred from the payment accounting date.",
    )
    _collection_payment_unique = models.Constraint(
        "UNIQUE(collection_payment_id)",
        "A payment can only be assigned to one construction advance.",
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

    mixed_taxes_confirmed = fields.Boolean(
        string="Mixed tax treatment reviewed",
        copy=False,
        help="Confirm that the selected taxes have been reviewed for this specific advance. "
             "If several tax treatments are applicable, create a separate advance for each one.",
    )

    @api.model
    def _has_mixed_order_taxes(self, order):
        lines = order.order_line.filtered(lambda line: not line.display_type and line.product_id)
        return bool(lines and any(line.tax_ids != lines[0].tax_ids for line in lines))

    @api.model
    def _default_taxes(self, sale_order):
        """Use shared taxes only; mixed treatments require explicit review."""
        lines = sale_order.order_line.filtered(lambda line: not line.display_type and line.product_id)
        if not lines:
            return self.env["account.tax"]
        first = lines[0].tax_ids
        if all(line.tax_ids == first for line in lines):
            return first
        return self.env["account.tax"]

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
        economic = {"sale_order_id", "date", "amount", "tax_ids", "mixed_taxes_confirmed", "collection_payment_id", "collection_date"}
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
                if new_state == "confirmed" and advance.state == "draft":
                    if economic.intersection(vals):
                        raise UserError(_("Save the advance details before confirming it."))
                    if advance._has_mixed_order_taxes(advance.sale_order_id) and not advance.mixed_taxes_confirmed:
                        raise UserError(_("Review the taxes for this mixed-tax order. If necessary create one advance per tax treatment, then confirm the review."))
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
            if advance._has_mixed_order_taxes(advance.sale_order_id) and not advance.mixed_taxes_confirmed:
                raise UserError(_("Review the taxes for this mixed-tax order. If necessary create one advance per tax treatment, then confirm the review."))
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
        self._check_general_vat_taxes(self.tax_ids)
        payment, payment_line = self._check_received_payment()
        if self.state != "confirmed":
            raise UserError(_("Only confirmed advances can be invoiced."))
        if self.invoice_id and self.invoice_id.state != "cancel":
            raise UserError(_("This advance already has an invoice."))
        if not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("Only billing users can invoice an advance."))
        if self._has_mixed_order_taxes(self.sale_order_id) and not self.mixed_taxes_confirmed:
            raise UserError(_("Review the taxes for this mixed-tax order. If necessary create one advance per tax treatment, then confirm the review."))
        order = self.sale_order_id
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": (order.partner_invoice_id or self.partner_id).id,
            "partner_shipping_id": order.partner_shipping_id.id,
            "fiscal_position_id": order.fiscal_position_id.id,
            "invoice_payment_term_id": order.payment_term_id.id,
            "document_tax_mode": "tax_excluded",
            "invoice_origin": self.name,
            "invoice_date": fields.Date.context_today(self),
            "date": self.collection_date,
            "delivery_date": self.collection_date,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "narration": _("Advance payment for construction works - %s") % self.name,
            "invoice_line_ids": [(0, 0, self._prepare_invoice_line_vals())],
        })
        if self.currency_id.compare_amounts(invoice.amount_total, payment.amount):
            raise UserError(_(
                "The advance invoice total must equal the received payment, "
                "including taxes. Adjust the base amount or taxes before invoicing."
            ))
        self.invoice_id = invoice.id
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
        }

    def _check_received_payment(self, require_unallocated=True):
        """Check the real Odoo payment, rather than treating a request as cash."""
        self.ensure_one()
        payment = self.collection_payment_id.exists()
        if not payment:
            raise UserError(_("Select the recorded customer payment for this advance."))
        if not self.collection_date or self.collection_date > fields.Date.context_today(self):
            raise UserError(_("Enter the actual receipt date; it cannot be in the future."))
        self.env.cr.execute("SELECT id FROM account_payment WHERE id = %s FOR UPDATE", [payment.id])
        payment.invalidate_recordset()
        partner = self.sale_order_id.partner_invoice_id or self.partner_id
        if (payment.payment_type != "inbound" or payment.partner_type != "customer"
                or payment.company_id != self.company_id
                or payment.currency_id != self.currency_id
                or payment.partner_id.commercial_partner_id != partner.commercial_partner_id):
            raise UserError(_("The payment must be an incoming customer payment for the same company, customer and currency."))
        if payment.state not in ("paid", "reconciled") or not payment.move_id or payment.move_id.state != "posted":
            raise UserError(_("The selected payment must have a posted accounting entry."))
        if not payment.is_matched:
            raise UserError(_("Match the received payment with the bank transaction before invoicing the advance."))
        lines = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
            and line.account_id.reconcile
        )
        if len(lines) != 1:
            raise UserError(_("The payment must contain exactly one reconcilable customer entry."))
        line = lines
        if require_unallocated:
            residual = line.amount_residual_currency if line.currency_id == self.currency_id else line.amount_residual
            if line.reconciled or self.currency_id.compare_amounts(-residual, payment.amount):
                raise UserError(_("The customer payment is already allocated or its open balance differs from the payment."))
        return payment, line

    def action_reconcile_received_payment(self):
        """Use the same outstanding-item reconciliation as the Odoo invoice widget."""
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("Only billing users can reconcile the advance payment."))
        invoice = self.invoice_id
        if not invoice or invoice.state != "posted":
            raise UserError(_("Post the advance invoice before reconciling its payment."))
        payment, line = self._check_received_payment()
        if self.currency_id.compare_amounts(invoice.amount_total, payment.amount):
            raise UserError(_("The invoice total differs from the received payment."))
        receivable = invoice.line_ids.filtered(
            lambda item: item.account_id == line.account_id and not item.reconciled
        )
        if not receivable:
            raise UserError(_("The invoice and payment do not share an open customer account."))
        invoice.js_assign_outstanding_line(line.id)
        invoice.invalidate_recordset()
        if not invoice.currency_id.is_zero(invoice.amount_residual):
            raise UserError(_("The advance invoice was not fully reconciled with the payment."))
        return True

    @api.model
    def _check_general_vat_taxes(self, taxes):
        """Do not silently use the special cash-basis tax workflow.

        This validation is intentionally limited to construction operations;
        it does not alter the accounting or Spanish localisation models.
        """
        deferred = taxes.flatten_taxes_hierarchy().filtered(
            lambda tax: tax.tax_exigibility == "on_payment"
        )
        if deferred:
            raise UserError(_(
                "Construction invoices currently support the general VAT regime only. "
                "Review these cash-basis taxes: %(taxes)s.",
                taxes=", ".join(deferred.mapped("display_name")),
            ))

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
