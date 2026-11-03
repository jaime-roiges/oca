# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def write(self, vals):
        # Draft advance invoices must not disappear while their liability is
        # being consumed on another certification.
        if vals.get("state") == "cancel":
            advances = self.env["construction.advance"].search([
                ("invoice_id", "in", self.ids),
            ])
            for advance in advances:
                if advance.application_ids.filtered(
                    lambda app: app.certification_id.state != "cancel"
                ):
                    raise UserError(_(
                        "Cannot cancel the advance invoice while its advance "
                        "is applied on active certifications."
                    ))
        res = super().write(vals)
        if "fiscal_position_id" in vals:
            # Only the construction lines. A normal invoice keeps the taxes
            # the user set: Odoo 20 does not recompute them on this change.
            lines = self.line_ids._construction_protected_lines().filtered(
                lambda line: line.parent_state != "posted"
            )
            if lines:
                lines._compute_tax_ids()
                lines._compute_price_unit()
        if vals.get("state") == "cancel":
            Certification = self.env["construction.certification"]
            for cert in Certification.search([
                ("invoice_id", "in", self.ids),
                ("state", "=", "invoiced"),
            ]):
                if cert.invoice_id.state == "cancel":
                    cert.write({"state": "cancel"})
            Advance = self.env["construction.advance"]
            for advance in Advance.search([
                ("invoice_id", "in", self.ids),
                ("state", "!=", "cancel"),
            ]):
                if advance.invoice_id.state == "cancel" and not advance.application_ids.filtered(
                    lambda app: app.certification_id.state != "cancel"
                ):
                    advance.write({"state": "cancel"})
        if vals.get("state") == "posted":
            # Not only action_post. A credit note posted by another path
            # still has to refresh the open origin.
            self.filtered("reversed_entry_id").line_ids._refresh_open_construction_origins()
        return res

    def action_post(self):
        # Recheck at posting: a manual reconciliation may have consumed the
        # balance since the release invoice was created in draft.
        releases = self.env["construction.certification"].search([
            ("invoice_id", "in", self.filtered(lambda move: move.state == "draft").ids),
            ("is_retention_liquidation", "=", True),
            ("state", "=", "invoiced"),
        ])
        for cert in releases:
            cert._check_ready_for_approval()
            cert._check_retention_invoice_lines()
        result = super().action_post()
        posted = self.filtered(lambda move: move.state == "posted")
        reversals = posted.filtered("reversed_entry_id")
        ordinary = posted - reversals
        ordinary._reconcile_construction_advances()
        ordinary._reconcile_construction_retentions()
        for reversal in reversals:
            reversal.reversed_entry_id._reconcile_construction_reversal(reversal)
        reversals._apply_construction_reversal()
        # A partial credit note does not change the certification state, so
        # origin would stay at the quantity that was billed. Refresh the open
        # certifications of the same orders.
        originals = reversals.mapped("reversed_entry_id")
        if originals:
            self.env["construction.certification"].search([
                ("invoice_id", "in", originals.ids),
            ])._recompute_open_certifications()
        applications = reversals.line_ids.mapped("construction_advance_application_id")
        if applications:
            advances = applications.advance_id
            advances._compute_amounts()
            advances._refresh_applied_state()
        return result

    def copy(self, default=None):
        default = dict(default or {})
        # A reversal always carries reversed_entry_id. Re-set the context here
        # so the line copy keeps the links even if an inner env dropped it.
        if default.get("reversed_entry_id") or self.env.context.get("construction_keep_links"):
            self = self.with_context(construction_keep_links=True)
        return super().copy(default)

    def _reverse_moves(self, default_values_list=None, cancel=False):
        # Odoo 20 copies the invoice without fields marked copy=False.
        # The credit note has to keep the construction links, or the
        # standard price and account computes replace the certified amounts.
        for move in self:
            sources = move.line_ids.filtered(lambda line: line.construction_adjustment_type == "retention")
            partials = sources.mapped("matched_debit_ids") | sources.mapped("matched_credit_ids")
            related = (partials.mapped("debit_move_id") | partials.mapped("credit_move_id")) - sources
            if related.filtered(lambda line: line.construction_adjustment_type == "retention_release"):
                raise UserError(_("Reverse the related retention releases before reversing their original invoice."))
        return super(
            AccountMove, self.with_context(construction_keep_links=True)
        )._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    def _construction_reversal_still_effective(self):
        """Resolve any chain of posted reversal-of-reversal documents.

        A refund reversed by an invoice is void, but becomes effective again
        if that counter-invoice is subsequently refunded. The chain is an
        acyclic reversed_entry_id graph created by Odoo.
        """
        self.ensure_one()
        if self.state != "posted":
            return False
        later = self.reversal_move_ids.filtered(lambda move: move.state == "posted")
        return not any(move._construction_reversal_still_effective() for move in later)

    def _construction_effective_refunds(self):
        """Posted direct credits whose net effect survives contra-reversals."""
        self.ensure_one()
        posted = self.reversal_move_ids.filtered(
            lambda move: move.state == "posted"
            and move.move_type in ("out_refund", "in_refund")
            and move.reversed_entry_id == self
        )
        return posted.filtered(lambda refund: refund._construction_reversal_still_effective())

    def _construction_cancel_or_reverse(self):
        """Cancel drafts or reverse a *fully outstanding* posted invoice.

        Never treat an existing partial credit note as a full reversal. An
        accountant must complete partial refunds explicitly, rather than
        generating a second full refund that would over-credit the customer.
        """
        reversals = self.env["account.move"]
        for move in self:
            if not move or move.state == "cancel":
                continue
            if move.state == "draft":
                move.button_cancel()
                continue
            if move.state != "posted":
                continue
            existing = move._construction_effective_refunds()
            if existing:
                if not move._construction_reversal_is_complete(move):
                    raise UserError(_(
                        "Invoice %(invoice)s has partial credit notes. Complete the "
                        "remaining refund from Accounting before cancelling the "
                        "certification or advance. Automatic cancellation is blocked "
                        "to prevent an unreversed balance."
                    ) % {"invoice": move.display_name})
                reversals |= existing
                continue
            adjustments = move.line_ids.filtered("construction_adjustment_type")
            partials = adjustments.mapped("matched_debit_ids") | adjustments.mapped("matched_credit_ids")
            related = (partials.mapped("debit_move_id") | partials.mapped("credit_move_id")) - adjustments
            if related.filtered(lambda line: line.construction_adjustment_type in ("retention_release", "advance")):
                raise UserError(_(
                    "This invoice has construction adjustments already applied or released. "
                    "Reverse the related operations before cancelling the original invoice."
                ))
            # Free the advance and retention items so the credit note can
            # close them. Existing customer payments remain allocated.
            move.line_ids.filtered("construction_adjustment_type").remove_move_reconcile()
            reversal = move._reverse_moves(cancel=False)
            reversal.filtered(lambda refund: refund.state == "draft").action_post()
            if not move._construction_reversal_is_complete(move):
                raise UserError(_(
                    "The generated credit note does not fully reverse the "
                    "construction invoice %s. The operation was rolled back."
                ) % move.display_name)
            reversals |= reversal
        return reversals

    def _reconcile_construction_reversal(self, reversal):
        """Close the original construction lines with the credit note.

        The receivable is matched only for the amount still open. A paid
        invoice keeps its payment; the credit note leaves a credit on the
        customer instead of undoing the collection.
        """
        self.ensure_one()
        refund = reversal[:1]
        if not refund:
            return
        for original in self.line_ids.filtered("construction_adjustment_type"):
            if not original.account_id.reconcile or original.reconciled:
                continue
            counterpart = refund.line_ids.filtered(
                lambda line: line.account_id == original.account_id
                and line.construction_adjustment_type == original.construction_adjustment_type
                and line.construction_certification_line_id == original.construction_certification_line_id
                and line.construction_advance_application_id == original.construction_advance_application_id
                and line.construction_retention_allocation_id == original.construction_retention_allocation_id
                and line.construction_advance_id == original.construction_advance_id
                and not line.reconciled
            )[:1]
            if counterpart:
                (original | counterpart).reconcile()
        receivable = self.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
        )
        refund_receivable = refund.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable" and not line.reconciled
        )
        if receivable and refund_receivable:
            (receivable | refund_receivable).reconcile()

    def _reconcile_construction_advances(self):
        """Match each posted deduction with the advance invoice, either way.

        Posting the origin invoice first used to look only at that move, so
        a later advance invoice never found the deduction.
        """
        advances = self.env["construction.advance"]
        for line in self.line_ids:
            if line.construction_advance_id:
                advances |= line.construction_advance_id
            elif line.construction_advance_application_id:
                advances |= line.construction_advance_application_id.advance_id
        for advance in advances:
            invoice = advance.invoice_id
            if not invoice or invoice.state != "posted":
                continue
            source = invoice.line_ids.filtered(
                lambda line: line.construction_advance_id == advance
                and line.account_id.reconcile
                and not line.reconciled
            )[:1]
            if not source:
                continue
            deductions = self.env["account.move.line"].search([
                ("construction_advance_application_id.advance_id", "=", advance.id),
                ("account_id", "=", source.account_id.id),
                ("move_id.state", "=", "posted"),
                ("reconciled", "=", False),
            ])
            for deduction in deductions:
                if source.reconciled:
                    break
                if not deduction.balance or not source.balance:
                    continue
                if (deduction.balance > 0) == (source.balance > 0):
                    continue
                (deduction | source).reconcile()

    def _reconcile_construction_retentions(self):
        """Match a release with the oldest open withholding of the same order.

        Posting a withholding does not reconcile it. A single call on every
        open line of the order used to close a new retention against another
        certification, or against a credit note that was still open.
        """
        releases = self.line_ids.filtered(
            lambda line: line.construction_adjustment_type == "retention_release"
            and line.account_id.reconcile
            and not line.reconciled
        )
        for release in releases:
            if release.reconciled:
                continue
            allocation = release.construction_retention_allocation_id
            if allocation:
                source = allocation.source_line_id
                if (source.reconciled or source.account_id != release.account_id
                        or source.partner_id != release.partner_id
                        or source.company_id != release.company_id
                        or source.balance * release.balance >= 0):
                    raise UserError(_("The selected retention can no longer be reconciled with its release."))
                (release | source).reconcile()
                if not release.reconciled:
                    raise UserError(_("The selected retention does not cover the complete release."))
                continue
            order = release.construction_certification_id.sale_order_id
            if not release.balance:
                continue
            want_withholding_debit = release.balance < 0
            candidates = self.env["account.move.line"].search([
                ("account_id", "=", release.account_id.id),
                ("construction_adjustment_type", "=", "retention"),
                ("move_id.state", "=", "posted"),
                ("reconciled", "=", False),
                ("partner_id", "=", release.partner_id.id),
                ("company_id", "=", release.company_id.id),
            ], order="date_maturity, date, id")
            for candidate in candidates:
                if release.reconciled:
                    break
                if candidate.reconciled or not candidate.balance:
                    continue
                if want_withholding_debit and candidate.balance <= 0:
                    continue
                if not want_withholding_debit and candidate.balance >= 0:
                    continue
                other = candidate.construction_certification_id.sale_order_id
                if order and other and other != order:
                    continue
                (release | candidate).reconcile()

    def _construction_reversal_is_complete(self, original):
        """Verify every work, rounding, retention and advance component.

        Comparing only product-line totals could silently cancel a certificate
        whose retention or advance was not reversed. Comparing the global
        invoice total could allow unrelated credits to conceal missing work.
        Both base and taxed total are checked, with quantities on work lines.
        """
        self.ensure_one()
        if original.state != "posted":
            return False
        currency = original.currency_id or original.company_id.currency_id
        refunds = original._construction_effective_refunds()
        if not refunds:
            return False

        def identity(line):
            return (
                line.construction_certification_line_id.id,
                line.construction_adjustment_type or "",
                line.construction_advance_application_id.id,
                line.construction_advance_id.id,
                line.construction_retention_allocation_id.id,
                line.account_id.id,
            )

        def grouped(lines):
            result = {}
            for line in lines:
                # Unlinked invoice lines must not be hidden behind a different
                # refund's total. A missing link makes automatic cancellation
                # unsafe and requires manual accounting verification.
                if not any(identity(line)[:4]):
                    return None
                key = identity(line)
                item = result.setdefault(key, [0.0, 0.0, 0.0])
                item[0] += abs(line.price_subtotal or 0.0)
                item[1] += abs(line.price_total or 0.0)
                if line.construction_certification_line_id and not line.construction_adjustment_type:
                    item[2] += abs(line.quantity or 0.0)
            return result

        originals = grouped(original.invoice_line_ids.filtered("account_id"))
        if not originals:
            return False
        returned = grouped(refunds.invoice_line_ids.filtered("account_id"))
        if returned is None:
            return False
        for key, (base, taxed, quantity) in originals.items():
            actual_base, actual_taxed, actual_qty = returned.get(key, (0.0, 0.0, 0.0))
            if currency:
                if currency.compare_amounts(actual_base, base) < 0:
                    return False
                if currency.compare_amounts(actual_taxed, taxed) < 0:
                    return False
            elif actual_base + 0.0001 < base or actual_taxed + 0.0001 < taxed:
                return False
            if actual_qty + 1e-6 < quantity:
                return False
        return True

    def _apply_construction_reversal(self):
        """Re-evaluate the original invoice after any depth of reversals."""
        Certification = self.env["construction.certification"]
        Advance = self.env["construction.advance"]
        originals = self.env["account.move"]
        for move in self.filtered("reversed_entry_id"):
            root = move
            visited = set()
            while root.reversed_entry_id and root.id not in visited:
                visited.add(root.id)
                root = root.reversed_entry_id
            if root.id in visited or root.move_type not in ("out_invoice", "in_invoice"):
                continue
            originals |= root

        for original in originals:
            fully_credited = original._construction_reversal_is_complete(original)
            credits = original._construction_effective_refunds()
            certificates = Certification.search([("invoice_id", "=", original.id)])
            for cert in certificates:
                if fully_credited and cert.state == "invoiced":
                    cert.write({
                        "reversal_invoice_id": credits[:1].id,
                        "state": "cancel",
                    })
                    cert.application_ids.advance_id._refresh_applied_state()
                elif not fully_credited and cert.state == "cancel" and cert.reversal_invoice_id:
                    cert._check_applications_fit()
                    cert.write({"state": "invoiced", "reversal_invoice_id": False})
                    cert.application_ids.advance_id._refresh_applied_state()
            advances = Advance.search([("invoice_id", "=", original.id)])
            for advance in advances:
                if fully_credited and advance.state != "cancel":
                    if advance.application_ids.filtered(
                        lambda app: app.certification_id.state != "cancel"
                    ):
                        raise UserError(_(
                            "Cannot fully refund advance %s while it is still "
                            "applied on active certifications."
                        ) % advance.display_name)
                    advance.write({"state": "cancel"})
                elif not fully_credited and advance.state == "cancel":
                    advance.write({"state": "confirmed"})
                    advance._refresh_applied_state()
