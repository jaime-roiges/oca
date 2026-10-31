# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ConstructionCertification(models.Model):
    _name = "construction.certification"
    _description = "Work Certification (Certificación de Obra)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True
    _certification_number_uniq = models.Constraint(
        "UNIQUE(sale_order_id, certification_number)",
        "Certification number must be unique per sales order.",
    )

    # Draft and measured certifications are not committed: they must not
    # change the origin or the amount already taken by another certification.
    _committed_states = ("approved", "invoiced")
    _open_states = ("draft", "measured")
    _locked_states = ("approved", "invoiced")

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        required=True,
        tracking=True,
        index=True,
        check_company=True,
        domain="[('state', 'in', ('sale', 'done'))]",
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        string="Project",
        related="sale_order_id.project_id",
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
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
        comodel_name="res.currency",
        related="sale_order_id.currency_id",
        store=True,
        readonly=True,
    )
    date = fields.Date(
        string="Certification Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    certification_number = fields.Integer(
        string="Certification Number",
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("measured", "Measured"),
            ("approved", "Approved"),
            ("invoiced", "Invoiced"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name="construction.certification.line",
        inverse_name="certification_id",
        string="Certification Lines",
        copy=True,
    )
    amount_certified_origin = fields.Monetary(
        string="Certified to Origin",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_certified_origin_net = fields.Monetary(
        string="Net Origin",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Certified origin after posted credit notes. The billed origin "
        "above does not move.",
    )
    amount_previously_invoiced = fields.Monetary(
        string="Previously Certified",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Amount to invoice of earlier approved or invoiced certifications. "
        "Drafts and measured certifications are not included.",
    )
    amount_to_invoice = fields.Monetary(
        string="Amount to Invoice",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    retention_percent = fields.Float(
        string="Retention %",
        digits=(16, 2),
        default=5.0,
        help="Guarantee retention percentage applied on the amount to invoice.",
    )
    amount_retention = fields.Monetary(
        string="Retention Amount",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_net_to_invoice = fields.Monetary(
        string="Net to Invoice",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_advance_applied = fields.Monetary(
        string="Advance Applied",
        currency_field="currency_id",
        compute="_compute_amount_advance_applied",
        inverse="_inverse_amount_advance_applied",
        store=True,
        copy=False,
        help="Sum of the application lines. Raising the total adds the "
        "difference on the oldest advances and does not move a line you "
        "already chose. Lowering it removes the difference from the latest "
        "advances first. Each application is deducted on its own invoice line.",
    )
    application_ids = fields.One2many(
        comodel_name="construction.advance.application",
        inverse_name="certification_id",
        string="Advance Applications",
        copy=False,
    )
    amount_final_to_invoice = fields.Monetary(
        string="Final to Invoice",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    is_retention_liquidation = fields.Boolean(
        string="Retention Liquidation",
        help="Check this if this certification is only for releasing previously retained amounts.",
    )
    retention_to_release = fields.Monetary(
        string="Retention to Release",
        currency_field="currency_id",
        help="On a normal certification this only reduces the retention withheld "
        "on the current period, and cannot exceed it. To pay back retention "
        "already invoiced, mark Retention Liquidation.",
    )
    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        readonly=True,
        copy=False,
    )
    reversal_invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Credit Note",
        readonly=True,
        copy=False,
        help="Credit note created when a posted origin invoice is cancelled.",
    )
    notes = fields.Text(string="Notes")
    progress_approver_id = fields.Many2one(
        comodel_name="res.partner",
        string="Progress Approver",
        compute="_compute_progress_approver",
    )

    @api.depends("project_id")
    def _compute_progress_approver(self):
        has_field = "x_progress_approver" in self.env["project.project"]._fields
        for cert in self:
            approver = False
            if has_field and cert.project_id:
                approver = cert.project_id["x_progress_approver"]
            cert.progress_approver_id = approver

    def _next_certification_numbers(self, vals_list):
        """Assign numbers under a row lock so two creates cannot share one."""
        next_number = {}
        for vals in vals_list:
            sale_order_id = vals.get("sale_order_id")
            if not sale_order_id or vals.get("certification_number"):
                continue
            if sale_order_id not in next_number:
                self.env.cr.execute(
                    "SELECT construction_last_certification_number FROM sale_order "
                    "WHERE id = %s FOR UPDATE",
                    [sale_order_id],
                )
                locked_row = self.env.cr.fetchone()
                if locked_row is None:
                    raise UserError(_("The sale order no longer exists."))
                self.env.cr.execute(
                    "SELECT COALESCE(MAX(certification_number), 0) "
                    "FROM %s WHERE sale_order_id = %%s" % self._table,
                    [sale_order_id],
                )
                # On existing databases seed the counter from issued rows.
                # Thereafter it survives unlink and remains monotone.
                existing_max = self.env.cr.fetchone()[0]
                next_number[sale_order_id] = max(locked_row[0] or 0, existing_max)
            next_number[sale_order_id] += 1
            vals["certification_number"] = next_number[sale_order_id]
        if next_number:
            for sale_order_id, last_number in next_number.items():
                self.env.cr.execute(
                    "UPDATE sale_order SET construction_last_certification_number = %s "
                    "WHERE id = %s",
                    [last_number, sale_order_id],
                )
            self.env["sale.order"].browse(list(next_number)).invalidate_recordset(
                ["construction_last_certification_number"]
            )

    @api.model_create_multi
    def create(self, vals_list):
        requested_advances = []
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                raise UserError(_("New certifications must start as draft."))
            if vals.get("invoice_id") or vals.get("reversal_invoice_id"):
                raise UserError(_("Invoices can only be linked to an existing certification."))
            # Application lines are the ledger. A typed total is allocated
            # only when the caller did not pass those lines.
            if "application_ids" in vals:
                vals.pop("amount_advance_applied", None)
                requested_advances.append(None)
            else:
                requested_advances.append(vals.pop("amount_advance_applied", None))
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "construction.certification"
                ) or _("New")
        self._next_certification_numbers(vals_list)
        if any(vals.get("state") in self._committed_states for vals in vals_list):
            self = self.with_context(construction_committing=True)
        records = super().create(vals_list)
        for record, amount in zip(records, requested_advances):
            if amount:
                record._allocate_advances(amount)
        return records

    def write(self, vals):
        """Guard financial transitions also when invoked through RPC/imports.

        A readonly form is not an accounting safeguard. In particular a
        cancelled certification must never free a still-posted invoice.
        """
        if "invoice_id" in vals:
            invoice = self.env["account.move"].browse(vals["invoice_id"]) if vals["invoice_id"] else False
            for cert in self:
                if cert.invoice_id and cert.invoice_id != invoice:
                    raise UserError(_("The certification's linked invoice cannot be replaced or cleared."))
                if invoice and (
                    invoice.move_type != "out_invoice"
                    or invoice.company_id != cert.company_id
                    or invoice.partner_id != (cert.sale_order_id.partner_invoice_id or cert.partner_id)
                ):
                    raise UserError(_("The linked invoice must belong to the same company and billing customer."))
            if invoice and not self.env.user.has_group("account.group_account_invoice"):
                raise UserError(_("Only billing users can attach a certification invoice."))
        if "reversal_invoice_id" in vals and not vals["reversal_invoice_id"]:
            for cert in self:
                if cert.reversal_invoice_id and (
                    vals.get("state") != "invoiced"
                    or not cert.invoice_id
                    or cert.invoice_id.state != "posted"
                    or cert.invoice_id._construction_reversal_is_complete(cert.invoice_id)
                ):
                    raise UserError(_("The credit-note link cannot be cleared while the invoice remains reversed."))
        if "reversal_invoice_id" in vals and vals["reversal_invoice_id"]:
            reversal = self.env["account.move"].browse(vals["reversal_invoice_id"])
            for cert in self:
                if (not cert.invoice_id or reversal.reversed_entry_id != cert.invoice_id
                        or reversal.state != "posted" or reversal.move_type != "out_refund"):
                    raise UserError(_("The reversal must be a posted credit note of this certification's invoice."))
        if "state" in vals:
            new_state = vals["state"]
            if new_state not in dict(self._fields["state"].selection):
                raise UserError(_("Unknown certification state."))
            for cert in self:
                if cert.state == new_state:
                    continue
                invoice = cert.invoice_id
                if new_state == "measured" and cert.state != "draft":
                    raise UserError(_("Only draft certifications can be measured."))
                if new_state == "approved" and cert.state not in self._open_states:
                    raise UserError(_("Only draft or measured certifications can be approved."))
                if new_state == "approved":
                    cert._check_approval_permission()
                if new_state in ("measured", "approved"):
                    cert._check_ready_for_approval()
                if cert.state == "invoiced" and new_state != "cancel":
                    raise UserError(_("An invoiced certification can only be cancelled."))
                if new_state == "cancel" and invoice:
                    if invoice.state == "draft":
                        raise UserError(_("Cancel the draft invoice before cancelling the certification."))
                    if invoice.state == "posted" and not invoice._construction_reversal_is_complete(invoice):
                        raise UserError(_(
                            "The origin invoice has not been fully reversed. "
                            "A partial credit note does not cancel the certification."
                        ))
                if cert.state == "cancel" and new_state != "cancel":
                    if invoice and invoice.state == "posted":
                        if new_state != "invoiced" or invoice._construction_reversal_is_complete(invoice):
                            raise UserError(_(
                                "A cancelled posted invoice cannot be reopened unless "
                                "its credit note has itself been reversed."
                            ))
                        cert._check_applications_fit()
                    elif new_state != "draft":
                        raise UserError(_("A cancelled certification can only return to draft."))
                if new_state == "invoiced":
                    if cert.state != "cancel":
                        cert._check_ready_for_approval()
                    invoice_id = vals.get("invoice_id", invoice.id)
                    if not invoice_id:
                        raise UserError(_("A certification cannot be invoiced without an invoice."))
                    if not self.env.user.has_group("account.group_account_invoice"):
                        raise UserError(_("Only billing users can mark certifications invoiced."))
        locked_fields = {
            "sale_order_id", "date", "line_ids", "retention_percent",
            "retention_to_release", "amount_advance_applied", "application_ids",
            "is_retention_liquidation",
        }
        if locked_fields.intersection(vals) and any(
            cert.state in self._locked_states for cert in self
        ):
            raise UserError(_("Approved or invoiced certifications cannot be modified."))
        if vals.get("state") in self._committed_states:
            self = self.with_context(construction_committing=True)
        # Lines win over a total sent in the same write: keep manual allocation.
        allocate_advance = (
            "amount_advance_applied" in vals and "application_ids" not in vals
        )
        requested_advance = vals.pop("amount_advance_applied", None)
        restoring = (
            self.filtered(lambda cert: cert.state == "cancel")
            if vals.get("state") == "invoiced" else self.browse()
        )
        res = super().write(vals)
        if restoring:
            # A new certification may have used the quantities freed by the
            # cancelled invoice. In that case reverting the credit is unsafe
            # and posting it is rolled back rather than over-certifying.
            restoring.line_ids._check_qty()
        if allocate_advance:
            for cert in self:
                current = cert._round(sum(cert.application_ids.mapped("amount")))
                target = cert._round(requested_advance or 0.0)
                if cert.currency_id.compare_amounts(current, target) != 0:
                    cert._allocate_advances(target)
        if {"date", "state"} & set(vals):
            self._recompute_open_certifications()
        return res

    def unlink(self):
        if any(cert.invoice_id for cert in self):
            raise UserError(_("Certifications with an invoice history cannot be deleted."))
        return super().unlink()

    def _round(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        return currency.round(amount) if currency else amount

    def _get_previous_certifications(self, states):
        self.ensure_one()
        if not self.sale_order_id or not self.date:
            return self.browse()
        cert_id = self._origin.id
        domain = [
            ("sale_order_id", "=", self.sale_order_id.id),
            ("state", "in", list(states)),
        ]
        if cert_id:
            domain += [
                ("id", "!=", cert_id),
                "|",
                ("date", "<", self.date),
                "&",
                ("date", "=", self.date),
                ("id", "<", cert_id),
            ]
        else:
            domain.append(("date", "<=", self.date))
        return self.search(domain)

    @api.depends(
        "line_ids.amount_origin",
        "line_ids.amount_origin_net",
        "sale_order_id",
        "date",
        "retention_percent",
        "amount_advance_applied",
        "is_retention_liquidation",
        "retention_to_release",
        "state",
    )
    def _compute_amounts(self):
        amount_fields = (
            "amount_certified_origin",
            "amount_previously_invoiced",
            "amount_to_invoice",
            "amount_retention",
            "amount_net_to_invoice",
            "amount_final_to_invoice",
        )
        frozen = self.filtered(lambda cert: cert.id and cert._amounts_are_frozen())
        stored = {}
        if frozen:
            frozen.env.cr.execute(
                "SELECT id, %s FROM %s WHERE id IN %%s" % (
                    ", ".join('"%s"' % column for column in amount_fields),
                    frozen._table,
                ),
                [tuple(frozen.ids)],
            )
            stored = {row[0]: row[1:] for row in frozen.env.cr.fetchall()}
        for cert in frozen:
            values = stored.get(cert.id, (0.0,) * len(amount_fields))
            for field_name, value in zip(amount_fields, values):
                cert[field_name] = value or 0.0
            previous = cert._get_previous_certifications(self._committed_states)
            cert.amount_certified_origin_net = cert._net_header_origin(
                cert.amount_certified_origin, previous
            )
        for cert in self - frozen:
            previous = cert._get_previous_certifications(self._committed_states)
            previously = cert._previous_production_amount(previous)
            # Only the present lines contribute to this period; absent lines
            # retain their last billed origin without being certified again.
            period_amount = cert._round(sum(cert.line_ids.mapped("amount_period")))
            amount_origin = cert._round(previously + period_amount)
            to_invoice = period_amount
            if cert.is_retention_liquidation:
                retention = 0.0
                to_invoice = cert._round(to_invoice + (cert.retention_to_release or 0.0))
            else:
                retention = to_invoice * (cert.retention_percent or 0.0) / 100.0
                retention = max(0.0, retention - (cert.retention_to_release or 0.0))
                retention = cert._round(retention)
            net = cert._round(to_invoice - retention)
            final = cert._round(net - (cert.amount_advance_applied or 0.0))
            cert.amount_certified_origin = amount_origin
            cert.amount_certified_origin_net = cert._net_header_origin(amount_origin, previous)
            cert.amount_previously_invoiced = previously
            cert.amount_to_invoice = to_invoice
            cert.amount_retention = retention
            cert.amount_net_to_invoice = net
            cert.amount_final_to_invoice = final

    def _net_header_origin(self, amount_origin, previous):
        """Net certified origin including prior work items absent this period.

        An isolated certification can contain just one of several budget
        lines, but refunds on the others still reduce the net origin.
        """
        self.ensure_one()
        lines = (previous | self).mapped("line_ids")
        returned = sum(lines._credited_amount().values()) if lines else 0.0
        return max(self._round((amount_origin or 0.0) - returned), 0.0)

    def _amounts_are_frozen(self):
        """Approved and invoiced figures stay as stored.

        The write that enters those states runs with ``construction_committing``
        so the amount is calculated once. A later recompute, including the one
        Odoo does when the module is updated, reads the stored row.
        """
        self.ensure_one()
        if self.state == "invoiced":
            return True
        # Reversing an invoice does not erase what was historically billed.
        # A cancelled certificate with a posted (now credited) invoice keeps
        # its original monetary snapshot in case the credit is later undone.
        if self.state == "cancel" and self.invoice_id.state == "posted":
            return True
        if self.state == "approved" and not self.env.context.get("construction_committing"):
            return True
        return False

    def _header_analytic_distribution(self):
        """Weighted analytic of every measured line, for retention and advances.

        A certification with two analytic accounts splits the retention and
        the advance in proportion to the measured amount. The largest line
        alone used to take the whole amount.
        """
        self.ensure_one()
        weighted = {}
        total = 0.0
        for line in self.line_ids:
            distribution = line._invoice_analytic_distribution() or {}
            amount = abs(line.amount_period or 0.0)
            if not distribution or not amount:
                continue
            total += amount
            for key, percent in distribution.items():
                weighted[key] = weighted.get(key, 0.0) + amount * (percent or 0.0) / 100.0
        if not total:
            return False
        return {key: 100.0 * value / total for key, value in weighted.items()}

    def _previous_production_amount(self, previous):
        """Production already taken. A liquidation's release is not production."""
        self.ensure_one()
        total = 0.0
        for cert in previous:
            period = cert.amount_to_invoice or 0.0
            if cert.is_retention_liquidation:
                period -= cert.retention_to_release or 0.0
            total += period
        return self._round(total)

    def _gross_period_retention(self):
        self.ensure_one()
        if self.is_retention_liquidation:
            return 0.0
        base = (self.amount_certified_origin or 0.0) - (self.amount_previously_invoiced or 0.0)
        if self.currency_id.compare_amounts(base, 0.0) <= 0:
            return 0.0
        return self._round(base * (self.retention_percent or 0.0) / 100.0)

    def _retention_held_from_previous(self):
        """Net retention already withheld on posted certifications.

        ``amount_retention`` is already net of a normal certification's own
        release. A liquidation pays retention out without reducing that field,
        so its release has to be subtracted once.
        """
        self.ensure_one()
        held = 0.0
        previous = self._get_previous_certifications(["invoiced"])
        for cert in previous:
            if cert.is_retention_liquidation:
                held -= cert.retention_to_release or 0.0
            else:
                held += cert.amount_retention or 0.0
        held -= self._credited_adjustment(previous, "retention")
        return self._round(held)

    def _credited_adjustment(self, certifications, adjustment_type):
        """Posted credit of a retention or advance deduction, not undone."""
        if not certifications:
            return 0.0
        lines = self.env["account.move.line"].search([
            ("construction_certification_id", "in", certifications.ids),
            ("construction_adjustment_type", "=", adjustment_type),
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_refund", "in_refund")),
            ("move_id.reversed_entry_id.move_type", "in", ("out_invoice", "in_invoice")),
        ])
        lines = self.env["construction.certification.line"]._without_reversed_credits(lines)
        return self._round(sum(abs(line.price_subtotal or 0.0) for line in lines))

    def _retention_releasable(self):
        """How much of ``retention_to_release`` this certification may use.

        A normal certification can only reduce the retention it withholds now.
        Paying back retention already invoiced is a liquidation, and it cannot
        exceed the balance still held.
        """
        self.ensure_one()
        if self.is_retention_liquidation:
            return max(self._retention_held_from_previous(), 0.0)
        return self._gross_period_retention()

    @api.constrains("date", "sale_order_id", "state")
    def _check_date_against_invoiced(self):
        for cert in self:
            if not cert.sale_order_id or not cert.date or cert.state == "cancel":
                continue
            later_committed = self.search_count([
                ("sale_order_id", "=", cert.sale_order_id.id),
                ("state", "in", list(self._committed_states)),
                ("id", "!=", cert.id),
                ("date", ">", cert.date),
            ])
            if later_committed:
                raise ValidationError(
                    _("The date cannot be earlier than an approved or invoiced certification of the same sales order.")
                )

    @api.constrains("retention_percent", "retention_to_release", "amount_advance_applied")
    def _check_amounts(self):
        for cert in self:
            if cert.retention_percent < 0 or cert.retention_percent > 100:
                raise ValidationError(_("Retention percent must be between 0 and 100."))
            if cert.currency_id.compare_amounts(cert.retention_to_release or 0.0, 0.0) < 0:
                raise ValidationError(_("Retention to release cannot be negative."))
            if cert.currency_id.compare_amounts(cert.amount_advance_applied or 0.0, 0.0) < 0:
                raise ValidationError(_("Applied advance cannot be negative."))

    @api.depends("application_ids.amount")
    def _compute_amount_advance_applied(self):
        for cert in self:
            cert.amount_advance_applied = cert._round(
                sum(cert.application_ids.mapped("amount"))
            )

    def _inverse_amount_advance_applied(self):
        """Kept so the total stays writable. Allocation happens in write/create.

        Doing it here as well would FIFO-rebuild lines that were saved in the
        same call.
        """
        return

    def _advance_free_balance(self, advance):
        """Pending amount of one advance, ignoring this certification.

        A deduction that was credited is free again. The application row
        stays, so the raw application total would hide that money.
        """
        self.ensure_one()
        others = advance.application_ids.filtered(
            lambda app: app.certification_id != self
            and app.certification_id.state != "cancel"
        )
        credited = advance._credited_deduction(others)
        free = advance.amount - sum(others.mapped("amount")) + credited
        return max(free, 0.0)

    def _available_advance_amount(self):
        self.ensure_one()
        advances = self.sale_order_id.advance_ids.filtered(
            lambda adv: adv.state in ("confirmed", "applied")
        )
        total = sum(self._advance_free_balance(advance) for advance in advances)
        return self._round(max(total, 0.0))

    def _allocate_advances(self, target):
        """Move the total up or down without discarding a chosen application.

        An increase is added FIFO on whatever balance is still free. A
        decrease is removed from the latest advances first. Existing rows
        keep their id, and a manual line is not replaced by an older advance.
        """
        self.ensure_one()
        if self.env.context.get("allocating_advances"):
            return
        self = self.with_context(allocating_advances=True)
        if self.state not in self._open_states:
            raise UserError(
                _("Advances can only be applied on draft or measured certifications.")
            )
        currency = self.currency_id
        target = self._round(target or 0.0)
        if currency.compare_amounts(target, 0.0) < 0:
            raise UserError(_("Applied advance cannot be negative."))
        available = self._available_advance_amount()
        if currency.compare_amounts(target, available) > 0:
            raise UserError(
                _("Cannot apply %(target)s of advances; only %(available)s is pending.")
                % {"target": target, "available": available}
            )
        current = {app.advance_id.id: app for app in self.application_ids}
        current_total = self._round(sum(self.application_ids.mapped("amount")))
        delta = self._round(target - current_total)
        advances = self.sale_order_id.advance_ids.filtered(
            lambda adv: adv.state in ("confirmed", "applied")
        ).sorted(lambda adv: (adv.date, adv.id))
        Application = self.env["construction.advance.application"]
        if currency.compare_amounts(delta, 0.0) > 0:
            remaining = delta
            for advance in advances:
                app = current.get(advance.id)
                already = app.amount if app else 0.0
                room = max(self._advance_free_balance(advance) - already, 0.0)
                take = self._round(min(room, remaining))
                if currency.compare_amounts(take, 0.0) <= 0:
                    continue
                if app:
                    app.amount = self._round(app.amount + take)
                else:
                    Application.create({
                        "advance_id": advance.id,
                        "certification_id": self.id,
                        "amount": take,
                    })
                remaining = self._round(remaining - take)
                if currency.compare_amounts(remaining, 0.0) <= 0:
                    break
            if currency.compare_amounts(remaining, 0.0) > 0:
                raise UserError(_("Could not allocate the full advance amount."))
        elif currency.compare_amounts(delta, 0.0) < 0:
            remaining = self._round(-delta)
            ordered_apps = self.application_ids.sorted(
                lambda app: (app.advance_id.date, app.advance_id.id, app.id),
                reverse=True,
            )
            for app in ordered_apps:
                if currency.compare_amounts(remaining, 0.0) <= 0:
                    break
                cut = self._round(min(app.amount, remaining))
                new_amount = self._round(app.amount - cut)
                if currency.compare_amounts(new_amount, 0.0) <= 0:
                    remaining = self._round(remaining - app.amount)
                    app.unlink()
                else:
                    app.amount = new_amount
                    remaining = self._round(remaining - cut)
            if currency.compare_amounts(remaining, 0.0) > 0:
                raise UserError(_("Could not reduce the applied advance by the requested amount."))

    def _check_applications_fit(self):
        self.ensure_one()
        totals = {}
        for app in self.application_ids:
            totals[app.advance_id] = totals.get(app.advance_id, 0.0) + app.amount
        for advance, amount in totals.items():
            if advance.state not in ("confirmed", "applied"):
                raise UserError(
                    _("Cannot reopen the certification: advance %s is cancelled.")
                    % advance.display_name
                )
            free = self._advance_free_balance(advance)
            if self.currency_id.compare_amounts(amount, free) > 0:
                raise UserError(
                    _("Cannot reopen the certification: advance %(advance)s only has %(free)s pending.")
                    % {"advance": advance.display_name, "free": free}
                )

    def action_measure(self):
        for cert in self:
            if not cert.line_ids and not cert.retention_to_release:
                raise UserError(_("Add certification lines or a retention release before confirming."))
            cert._check_ready_for_approval()
        self.write({"state": "measured"})

    def _check_approval_permission(self):
        """Opt-in separation of duties, enforced also on direct ORM writes."""
        self.ensure_one()
        if self.company_id.construction_approval_policy != "restricted":
            return
        if self.env.su or self.env.user.has_group("sales_team.group_sale_manager"):
            return
        approver = self.progress_approver_id
        if approver and self.env.user.partner_id == approver:
            return
        raise UserError(_(
            "Only a Sales Manager or the designated project progress "
            "approver can approve this construction certification."
        ))

    def action_approve(self):
        for cert in self:
            cert._check_ready_for_approval()
        self.write({"state": "approved"})

    def _check_ready_for_approval(self):
        self.ensure_one()
        # Also enforced for RPC/imports that write state='approved' directly.
        # A BC3 reimport can intentionally clear a previous draft when the
        # corrected cumulative origin no longer adds any work.
        if not self.line_ids and not self.retention_to_release:
            raise UserError(_(
                "A certification without work lines or a retention release "
                "cannot be measured or approved."
            ))
        self.line_ids._check_qty()
        currency = self.currency_id
        releasable = self._retention_releasable()
        if self.retention_to_release and currency.compare_amounts(self.retention_to_release, releasable) > 0:
            if self.is_retention_liquidation:
                message = _(
                    "Retention to release (%(release)s) exceeds the retention still held (%(available)s)."
                )
            else:
                message = _(
                    "Retention to release (%(release)s) exceeds this period's retention (%(available)s). "
                    "Use a retention liquidation to pay back retention that was already invoiced."
                )
            raise UserError(message % {"release": self.retention_to_release, "available": releasable})
        if currency.compare_amounts(self.amount_advance_applied or 0.0, 0.0) > 0:
            if currency.compare_amounts(self.amount_advance_applied, self.amount_net_to_invoice) > 0:
                raise UserError(
                    _("Applied advance cannot be greater than the net amount to invoice.")
                )
        if currency.compare_amounts(self.amount_final_to_invoice, 0.0) < 0:
            raise UserError(_("The final amount to invoice cannot be negative."))

    def action_cancel(self):
        invoiced = self.filtered(lambda cert: cert.invoice_id and cert.invoice_id.state != "cancel")
        if invoiced and not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("Only billing users can cancel a certification that has an invoice."))
        for cert in self:
            reversal = cert.invoice_id._construction_cancel_or_reverse()
            if reversal and not cert.reversal_invoice_id:
                cert.reversal_invoice_id = reversal[:1].id
        advances = self.application_ids.advance_id
        still_open = self.filtered(lambda cert: cert.state != "cancel")
        if still_open:
            still_open.write({"state": "cancel"})
        advances._refresh_applied_state()

    def _recompute_open_certifications(self):
        """Refresh every open certification of these orders, including ones with no lines.

        Invoiced certifications are left untouched: their stored origin is the
        figure that was billed.
        """
        orders = self.mapped("sale_order_id")
        if not orders:
            return
        open_states = self._open_states
        certs = self.search([
            ("sale_order_id", "in", orders.ids),
            ("state", "in", open_states),
        ])
        if certs.line_ids:
            certs.line_ids._compute_origin()
            certs.line_ids._compute_amounts()
        if certs:
            certs._compute_amounts()

    def action_draft(self):
        for cert in self:
            if cert.state == "invoiced":
                raise UserError(_("Invoiced certifications cannot be reset to draft."))
            if cert.state == "cancel":
                cert._check_applications_fit()
        advances = self.application_ids.advance_id
        self.write({"state": "draft"})
        advances._refresh_applied_state()

    def action_apply_advance(self):
        """Add pending advances up to the net amount, without reshuffling.

        Existing application lines stay. Only the difference is added, on the
        oldest advances that still have a balance. If the lines already exceed
        the net amount, the user has to lower them.
        """
        for cert in self:
            if cert.state not in self._open_states:
                raise UserError(_("Advances can only be applied on draft or measured certifications."))
            pending = cert._available_advance_amount()
            net = max(cert.amount_net_to_invoice or 0.0, 0.0)
            target = cert._round(min(pending, net))
            current = cert._round(sum(cert.application_ids.mapped("amount")))
            if cert.currency_id.compare_amounts(current, target) > 0:
                raise UserError(
                    _("Applied advances (%(current)s) exceed the net amount (%(target)s). "
                      "Reduce the lines on the Advances tab.")
                    % {"current": current, "target": target}
                )
            if cert.currency_id.compare_amounts(current, target) < 0:
                cert.amount_advance_applied = target

    def action_create_invoice(self):
        """Create origin-based invoice (facturación a origen)."""
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only approved certifications can be invoiced."))
        if not self.env.user.has_group("account.group_account_invoice"):
            raise UserError(_("Only billing users can create the origin invoice."))
        if self.invoice_id and self.invoice_id.state != "cancel":
            raise UserError(_("This certification is already invoiced."))
        self._check_ready_for_approval()
        if self.currency_id.is_zero(self.amount_final_to_invoice) and self.currency_id.is_zero(self.amount_to_invoice):
            raise UserError(_("There is nothing to invoice."))
        # A fully deducted advance can give a zero net invoice. The work and
        # VAT regularisation must still be documented on that invoice.
        self._check_advances_charged()
        self._check_forced_included_taxes()

        invoice_vals = self._prepare_invoice_vals()
        invoice = self.env["account.move"].create(invoice_vals)
        self._absorb_invoice_rounding(invoice)
        if self.currency_id.compare_amounts(invoice.amount_untaxed, self.amount_final_to_invoice) != 0:
            raise UserError(
                _("The invoice untaxed amount (%(invoice)s) does not match the certification (%(cert)s).")
                % {"invoice": invoice.amount_untaxed, "cert": self.amount_final_to_invoice}
            )
        self.write({
            "invoice_id": invoice.id,
            "state": "invoiced",
        })
        self.application_ids.mapped("advance_id")._refresh_applied_state()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "target": "current",
        }

    def _check_advances_charged(self):
        """An applied advance must have a real posted accounting document.

        Even an untaxed advance creates a liability: a confirmation alone is
        not a posting and must never be used to reduce the origin invoice.
        """
        self.ensure_one()
        for application in self.application_ids:
            advance = application.advance_id
            invoice = advance.invoice_id
            if not invoice or invoice.state != "posted":
                raise UserError(
                    _("Post the invoice of advance %s before deducting it, "
                      "including when the advance has no taxes.")
                    % advance.display_name
                )

    def _check_forced_included_taxes(self):
        """Odoo 20 lets a tax ignore the invoice tax mode.

        ``price_include_override = tax_included`` treats the unit price as
        already taxed. The invoice can only be built when every tax on it is
        a percent tax of that kind, or none of them is.
        """
        self.ensure_one()
        lines = self.env["account.move.line"]
        groups = [line.sale_line_id.tax_ids for line in self.line_ids]
        groups += [application.advance_id._taxes_charged() for application in self.application_ids]
        for taxes in groups:
            if lines._included_tax_rate(taxes) is False:
                flat = lines._flatten_construction_taxes(taxes)
                raise UserError(
                    _("Tax %s forces a tax-included price and cannot be mixed or used as a fixed amount on a certification invoice.")
                    % ", ".join((flat or taxes).mapped("display_name"))
                )

    def _expected_excluded(self, line):
        """Excluded base this invoice line should carry."""
        self.ensure_one()
        currency = self.currency_id
        if line.construction_adjustment_type == "rounding" and line.construction_certification_line_id:
            amount = line.construction_certification_line_id._invoice_rounding_amount()
        elif line.construction_advance_application_id:
            amount = -line.construction_advance_application_id.amount
        elif line.construction_adjustment_type == "retention":
            amount = -(self.amount_retention or 0.0)
        elif line.construction_adjustment_type == "retention_release":
            amount = self.retention_to_release or 0.0
        elif line.construction_certification_line_id:
            _qty, unit = line.construction_certification_line_id._invoice_quantity_price()
            amount = (line.quantity or _qty or 1.0) * unit
        else:
            amount = line.price_subtotal or 0.0
        return currency.round(amount) if currency else amount

    def _absorb_invoice_rounding(self, invoice):
        """A tax computation in Odoo 20 can leave the base a cent off.

        The cent goes on the line whose excluded base does not match, not on
        the first product line. It is stored, so a later recompute keeps it.
        Anything larger than five cents is a real mismatch.
        """
        self.ensure_one()
        currency = self.currency_id
        for _step in range(3):
            diff = currency.round(self.amount_final_to_invoice - invoice.amount_untaxed)
            if currency.is_zero(diff) or currency.compare_amounts(abs(diff), 0.05) > 0:
                return
            candidates = invoice.invoice_line_ids.filtered(
                lambda item: item.construction_certification_line_id
                or item.construction_adjustment_type
                or item.construction_advance_application_id
            )
            line = self.env["account.move.line"]
            widest = 0.0
            for candidate in candidates:
                if not candidate.quantity:
                    continue
                gap = abs(self._expected_excluded(candidate) - (candidate.price_subtotal or 0.0))
                if currency.compare_amounts(gap, widest) > 0:
                    widest = gap
                    line = candidate
            if not line:
                line = candidates.filtered(lambda item: item.quantity)[:1]
            if not line:
                return
            rate = line._included_tax_rate(line.tax_ids) or 0.0
            factor = (1.0 + rate / 100.0) if rate else 1.0
            delta = (diff / line.quantity) * factor
            # Only the stored adjust. It is a dependency of price_unit, so
            # writing it already recomputes the price. Adding delta to
            # price_unit as well counted the cent twice.
            line.construction_price_adjust = (line.construction_price_adjust or 0.0) + delta
            line._apply_construction_price()

    def _prepare_invoice_vals(self):
        self.ensure_one()
        invoice_line_vals = []
        # Negative contractual lines (BC3 award discounts, etc.) are real
        # taxable invoice rows.  Skip only zero movements, not negative bases.
        for line in self.line_ids.filtered(
            lambda item: not self.currency_id.is_zero(item.amount_period or 0.0)
        ):
            invoice_line_vals.append((0, 0, line._prepare_invoice_line_vals()))
            rounding = line._prepare_rounding_line_vals()
            if rounding:
                invoice_line_vals.append((0, 0, rounding))

        # Add retention / advance adjustment lines so the invoice total matches amount_final_to_invoice
        if self.amount_retention:
            invoice_line_vals.append((0, 0, self._prepare_adjustment_line(
                _("Guarantee Retention (%s%%)") % self.retention_percent,
                -self.amount_retention,
                self.company_id._get_construction_retention_account(),
                "retention",
            )))
        for application in self.application_ids.sorted(
            lambda app: (app.advance_id.date, app.advance_id.id, app.id)
        ):
            line_vals = self._prepare_adjustment_line(
                _("Advance applied: %s") % application.advance_id.display_name,
                -application.amount,
                self.company_id._get_construction_advance_account(),
                "advance",
            )
            line_vals["construction_advance_application_id"] = application.id
            line_vals["tax_ids"] = [(6, 0, application.advance_id._taxes_charged().ids)]
            invoice_line_vals.append((0, 0, line_vals))
        if self.retention_to_release and self.is_retention_liquidation:
            invoice_line_vals.append((0, 0, self._prepare_adjustment_line(
                _("Retention Released"),
                self.retention_to_release,
                self.company_id._get_construction_retention_account(),
                "retention_release",
            )))
        if not invoice_line_vals:
            raise UserError(_("There are no invoiceable lines on this certification."))

        order = self.sale_order_id
        invoice_partner = order.partner_invoice_id or order.partner_id
        return {
            "move_type": "out_invoice",
            "partner_id": invoice_partner.id,
            "partner_shipping_id": order.partner_shipping_id.id,
            "fiscal_position_id": order.fiscal_position_id.id,
            "invoice_payment_term_id": order.payment_term_id.id,
            # Prices on the certification are tax-excluded bases (discount and
            # tax-included sale prices are converted). VAT is added by tax_ids.
            "document_tax_mode": "tax_excluded",
            "invoice_origin": self.name,
            "invoice_date": self.date,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "narration": _(
                "Certification %s\n"
                "Certified to Origin: %s\n"
                "Previously Certified: %s\n"
                "Amount to Invoice: %s\n"
                "Retention (%s%%): %s\n"
                "Advance Applied: %s\n"
                "Retention Released: %s\n"
                "Final to Invoice: %s"
            ) % (
                self.name,
                self.amount_certified_origin,
                self.amount_previously_invoiced,
                self.amount_to_invoice,
                self.retention_percent,
                self.amount_retention,
                self.amount_advance_applied,
                self.retention_to_release,
                self.amount_final_to_invoice,
            ),
            "invoice_line_ids": invoice_line_vals,
        }

    def _prepare_adjustment_line(self, name, amount, account, adjustment_type):
        self.ensure_one()
        return {
            "name": name,
            "quantity": 1.0,
            "price_unit": amount,
            "account_id": account.id,
            "construction_certification_id": self.id,
            "construction_adjustment_type": adjustment_type,
            **self._analytic_vals(),
        }

    def _analytic_vals(self):
        distribution = self._header_analytic_distribution()
        if distribution and "analytic_distribution" in self.env["account.move.line"]._fields:
            return {"analytic_distribution": distribution}
        return {}

    def action_view_invoice(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.invoice_id.id,
            "view_mode": "form",
        }
