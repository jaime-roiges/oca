# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round

# Approved and invoiced certifications are committed. Drafts and measured
# ones are still editable and must not move the origin of anything else.
COMMITTED_STATES = ("approved", "invoiced")
OPEN_STATES = ("draft", "measured")
LOCKED_STATES = ("approved", "invoiced")


class ConstructionCertificationLine(models.Model):
    _name = "construction.certification.line"
    _description = "Work Certification Line"
    _order = "sequence, id"

    _certification_sale_line_uniq = models.Constraint(
        "UNIQUE(certification_id, sale_line_id)",
        "Each sales order line can appear only once on a certification.",
    )

    certification_id = fields.Many2one(
        comodel_name="construction.certification",
        string="Certification",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="certification_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sale Order Line",
        required=True,
        domain="[('order_id', '=', parent.sale_order_id), ('display_type', '=', False)]",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        related="sale_line_id.product_id",
        store=True,
        readonly=True,
    )
    name = fields.Text(
        string="Description",
        related="sale_line_id.name",
        readonly=True,
    )
    reference = fields.Char(
        string="Reference",
        compute="_compute_reference",
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="sale_line_id.product_uom_id",
        readonly=True,
    )
    product_uom_qty = fields.Float(
        string="Budgeted Qty",
        related="sale_line_id.product_uom_qty",
        readonly=True,
    )
    # Snapshot. A related price would rewrite invoiced certifications
    # when the budget changes.
    price_unit = fields.Float(
        string="Unit Price",
        digits="Product Price",
    )
    currency_id = fields.Many2one(
        related="certification_id.currency_id",
        store=True,
    )

    mrp_cumulated_qty = fields.Float(
        string="MRP Cumulated Qty",
        compute="_compute_mrp_progress",
        digits="Product Unit of Measure",
    )
    mrp_cumulated_percent = fields.Float(
        string="MRP Cumulated %",
        compute="_compute_mrp_progress",
        digits=(16, 4),
    )

    qty_period = fields.Float(
        string="Qty This Period",
        digits="Product Unit of Measure",
    )
    # Ratio 0–1 so the percentage widget shows 50% for half the budget.
    percent_period = fields.Float(
        string="% This Period",
        digits=(16, 4),
    )
    qty_origin = fields.Float(
        string="Quantity to Origin",
        compute="_compute_origin",
        store=True,
        digits="Product Unit",
        help="Certified quantity to origin, the same quantity the origin amount is built from. Credit notes are not subtracted here.",
    )
    qty_origin_net = fields.Float(
        string="Net Quantity to Origin",
        compute="_compute_origin",
        store=True,
        digits="Product Unit",
        help="Quantity to origin after posted credit notes. This is what the budget check uses.",
    )
    percent_origin_net = fields.Float(
        string="Net % to Origin",
        compute="_compute_origin",
        store=True,
        digits=(16, 4),
        help="Percent of the budget still certified after posted credit notes.",
    )
    amount_origin_net = fields.Monetary(
        string="Net Amount to Origin",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
        help="Billed origin amount minus the excluded amount of posted credit notes. Not a share of the billed amount.",
    )
    percent_origin = fields.Float(
        string="% to Origin",
        compute="_compute_origin",
        store=True,
        digits=(16, 4),
    )
    amount_period = fields.Monetary(
        string="Amount This Period",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_origin = fields.Monetary(
        string="Amount to Origin",
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    invoice_line_ids = fields.One2many(
        comodel_name="account.move.line",
        inverse_name="construction_certification_line_id",
        string="Invoice Lines",
    )

    def _locked(self):
        return self.filtered(lambda line: line.certification_id.state in LOCKED_STATES)

    def _check_editable(self):
        locked = self._locked()
        if locked:
            raise UserError(
                _("Lines of an approved or invoiced certification cannot be modified.")
            )

    @api.model
    def _measurement_vals(self, vals):
        """Keep quantity and percent on the same scale, and copy the price."""
        vals = dict(vals)
        sale_line = self.env["sale.order.line"].browse(vals.get("sale_line_id"))
        budget = sale_line.product_uom_qty if sale_line else 0.0
        if sale_line and "price_unit" not in vals:
            vals["price_unit"] = self._certified_price_unit(sale_line)
        if budget:
            if "qty_period" in vals and "percent_period" not in vals:
                vals["percent_period"] = (vals.get("qty_period") or 0.0) / budget
            elif "percent_period" in vals and "qty_period" not in vals:
                vals["qty_period"] = (vals.get("percent_period") or 0.0) * budget
        return vals

    @api.model
    def _ratio(self, value):
        """Accept either a 0–1 ratio or a 0–100 percentage from Studio."""
        value = value or 0.0
        if abs(value) > 1.0:
            return value / 100.0
        return value

    @api.model
    def _certified_price_unit(self, sale_line):
        """Tax-excluded unit price after the sales discount.

        Odoo 20 keeps the typed price in ``price_unit``. ``price_reduce_taxexcl``
        is ``price_subtotal / qty``, so a discount and a tax-included order
        are both reduced to the base that the origin invoice will tax once.
        """
        if not sale_line:
            return 0.0
        if sale_line.product_uom_qty:
            return sale_line.price_reduce_taxexcl
        discount = sale_line.discount or 0.0
        return sale_line.price_unit * (1.0 - discount / 100.0)

    def _invoice_analytic_distribution(self):
        """Copy the sale line distribution, or the project's analytic account."""
        self.ensure_one()
        if "analytic_distribution" not in self.env["account.move.line"]._fields:
            return False
        sale_line = self.sale_line_id
        if "analytic_distribution" in sale_line._fields and sale_line.analytic_distribution:
            return sale_line.analytic_distribution
        project = sale_line.order_id.project_id
        analytic = project.account_id if project and "account_id" in project._fields else False
        if analytic and analytic._name == "account.analytic.account":
            return {str(analytic.id): 100.0}
        return False

    @api.depends("sale_line_id")
    def _compute_reference(self):
        has_field = "x_reference" in self.env["sale.order.line"]._fields
        for line in self:
            line.reference = line.sale_line_id["x_reference"] if has_field and line.sale_line_id else False

    @api.model
    def _sale_line_mrp_progress(self, sale_line):
        """Read cumulative progress once per sale line, never once per MO.

        The industry field ``x_cumulated_qty`` on each related production is
        cumulative for the work item. Summing several copies of that total
        overstates production. The sale line's own total takes precedence
        when a newer industry version exposes it directly.
        """
        if not sale_line:
            return 0.0, 0.0
        if "x_cumulated_qty" in sale_line._fields:
            qty = sale_line.x_cumulated_qty or 0.0
        elif "x_production_ids" in sale_line._fields:
            productions = sale_line.x_production_ids
            qty = max(productions.mapped("x_cumulated_qty") or [0.0]) if (
                productions and "x_cumulated_qty" in productions._fields
            ) else 0.0
        else:
            qty = 0.0
        budget = sale_line.product_uom_qty or 0.0
        if budget:
            percent = qty / budget
        elif "x_cumulated_percent" in sale_line._fields:
            percent = self._ratio(sale_line.x_cumulated_percent)
        else:
            productions = sale_line.x_production_ids if "x_production_ids" in sale_line._fields else False
            percent = max(
                (self._ratio(value) for value in productions.mapped("x_cumulated_percent")),
                default=0.0,
            ) if productions and "x_cumulated_percent" in productions._fields else 0.0
        return qty, percent

    @api.depends("sale_line_id")
    def _compute_mrp_progress(self):
        for line in self:
            qty, percent = self._sale_line_mrp_progress(line.sale_line_id)
            line.mrp_cumulated_qty = qty
            line.mrp_cumulated_percent = percent

    @api.onchange("percent_period")
    def _onchange_percent_period(self):
        if self.product_uom_qty and not self.env.context.get("skip_measurement_sync"):
            self.with_context(skip_measurement_sync=True).qty_period = (
                self.percent_period or 0.0
            ) * self.product_uom_qty

    @api.onchange("qty_period")
    def _onchange_qty_period(self):
        if self.product_uom_qty and not self.env.context.get("skip_measurement_sync"):
            self.with_context(skip_measurement_sync=True).percent_period = (
                (self.qty_period or 0.0) / self.product_uom_qty
            )

    def _stored_values(self, columns):
        """Read stored columns without going through the compute cache."""
        if not self.ids:
            return {}
        self.env.cr.execute(
            'SELECT id, %s FROM %s WHERE id IN %%s' % (
                ", ".join('"%s"' % column for column in columns),
                self._table,
            ),
            [tuple(self.ids)],
        )
        rows = {}
        for row in self.env.cr.fetchall():
            rows[row[0]] = row[1:]
        return rows

    @api.depends(
        "qty_period",
        "sale_line_id",
        "certification_id.date",
        "certification_id.state",
        "invoice_line_ids.quantity",
        "invoice_line_ids.move_id.state",
        "invoice_line_ids.move_id.reversed_entry_id",
    )
    def _compute_origin(self):
        frozen = self.filtered(lambda line: line.id and line.certification_id._amounts_are_frozen())
        stored = frozen._stored_values(["qty_origin", "percent_origin"])
        for line in frozen:
            qty_origin, percent_origin = stored.get(line.id, (0.0, 0.0))
            line.qty_origin = qty_origin or 0.0
            line.percent_origin = percent_origin or 0.0
            line._assign_net_origin(line.qty_origin)
        for line in self - frozen:
            if not line.sale_line_id or not line.certification_id.date:
                line.qty_origin = line.qty_period or 0.0
                line._assign_net_origin(line.qty_origin)
                line.percent_origin = 0.0
                continue
            cert = line.certification_id
            cert_id = cert._origin.id
            domain = [
                ("sale_line_id", "=", line.sale_line_id.id),
                ("certification_id.state", "in", list(COMMITTED_STATES)),
            ]
            if cert_id:
                domain += [
                    ("certification_id", "!=", cert_id),
                    "|",
                    ("certification_id.date", "<", cert.date),
                    "&",
                    ("certification_id.date", "=", cert.date),
                    ("certification_id", "<", cert_id),
                ]
            previous_lines = self.search(domain)
            prev_qty = sum(previous_lines.mapped("qty_period"))
            gross = prev_qty + (line.qty_period or 0.0)
            line.qty_origin = gross
            line._assign_net_origin(gross)
            if line.product_uom_qty:
                line.percent_origin = line.qty_origin / line.product_uom_qty
            else:
                line.percent_origin = 0.0

    def _assign_net_origin(self, gross):
        """Net quantity, percent and amount. The billed figures stay put.

        The form shows the billed row and the net row apart, so an invoiced
        certification does not put the billed amount next to the net quantity.
        """
        self.ensure_one()
        credit = self._origin_credit()
        net = max((gross or 0.0) - credit, 0.0)
        self.qty_origin_net = net
        budget = self.product_uom_qty or 0.0
        self.percent_origin_net = net / budget if budget else 0.0

    @api.constrains("qty_period", "sale_line_id", "certification_id")
    def _check_qty(self):
        for line in self:
            if line.certification_id.state == "cancel":
                continue
            if line.qty_period < 0:
                raise ValidationError(_("Certified quantity cannot be negative."))
            if (
                line.sale_line_id
                and line.certification_id.sale_order_id
                and line.sale_line_id.order_id != line.certification_id.sale_order_id
            ):
                raise ValidationError(
                    _("The sales order line does not belong to this certification's order.")
                )
            if line.sale_line_id.display_type:
                raise ValidationError(_("Section and note lines cannot be certified."))
            if (
                line.product_uom_qty
                and not self.env.context.get("allow_over_certification")
            ):
                siblings = self.search([
                    ("sale_line_id", "=", line.sale_line_id.id),
                    ("id", "!=", line.id),
                    ("certification_id.state", "!=", "cancel"),
                ])
                credited = (line | siblings)._credited_quantity()
                standard = 0.0
                if line.sale_line_id:
                    standard = line.sale_line_id._prepare_qty_invoiced().get(line.sale_line_id, 0.0)
                total_qty = (
                    (line.qty_period or 0.0) - credited.get(line.id, 0.0)
                    + sum((item.qty_period or 0.0) - credited.get(item.id, 0.0) for item in siblings)
                    + standard
                )
                if total_qty > line.product_uom_qty + 1e-6:
                    raise ValidationError(
                        _("Certified quantity (%(total)s) exceeds the budgeted quantity (%(budget)s) on %(name)s. "
                          "Quantities already invoiced from the sales order are included.")
                        % {
                            "total": total_qty,
                            "budget": line.product_uom_qty,
                            "name": line.sale_line_id.display_name,
                        }
                    )
            if (
                line.product_uom_qty
                and not self.env.context.get("allow_over_certification")
                and line.qty_origin_net > line.product_uom_qty + 1e-6
            ):
                raise ValidationError(
                    _("Certified quantity to origin (%(origin)s) exceeds the budgeted quantity (%(budget)s) on %(name)s.")
                    % {
                        "origin": line.qty_origin_net,
                        "budget": line.product_uom_qty,
                        "name": line.sale_line_id.display_name,
                    }
                )

    def _origin_credit(self):
        """Posted credit quantity of this line and the ones in its origin."""
        self.ensure_one()
        if not self.sale_line_id or not self.certification_id.date:
            return 0.0
        cert = self.certification_id
        cert_id = cert._origin.id
        domain = [
            ("sale_line_id", "=", self.sale_line_id.id),
            ("certification_id.state", "in", list(COMMITTED_STATES)),
        ]
        if cert_id:
            domain += [
                ("certification_id", "!=", cert_id),
                "|",
                ("certification_id.date", "<", cert.date),
                "&",
                ("certification_id.date", "=", cert.date),
                ("certification_id", "<", cert_id),
            ]
        credited = (self.search(domain) | self)._credited_quantity()
        return sum(credited.values())

    def _credited_quantity(self):
        """Quantity reversed by posted credit notes, per certification line.

        A partial credit note keeps the certification invoiced. The reversed
        quantity has to leave the budget, or the same work cannot be certified
        again after the customer was refunded.
        """
        lines = self.env["account.move.line"].search([
            ("construction_certification_line_id", "in", self.ids),
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_refund", "in_refund")),
            ("move_id.reversed_entry_id.move_type", "in", ("out_invoice", "in_invoice")),
            ("construction_adjustment_type", "=", False),
        ])
        lines = self._without_reversed_credits(lines)
        credited = {}
        for line in lines:
            key = line.construction_certification_line_id.id
            credited[key] = credited.get(key, 0.0) + abs(line.quantity or 0.0)
        return credited

    @api.depends(
        "qty_period",
        "price_unit",
        "sale_line_id",
        "certification_id.date",
        "certification_id.state",
        "qty_origin",
        "qty_origin_net",
    )
    def _compute_amounts(self):
        frozen = self.filtered(lambda line: line.id and line.certification_id._amounts_are_frozen())
        stored = frozen._stored_values(["amount_period", "amount_origin"])
        for line in frozen:
            amount_period, amount_origin = stored.get(line.id, (0.0, 0.0))
            line.amount_period = amount_period or 0.0
            line.amount_origin = amount_origin or 0.0
            line.amount_origin_net = line._net_origin_amount()
        for line in self - frozen:
            # Value already billed stays at the price of that certification.
            # Repricing the budget must not revalue it.
            previous_amount = 0.0
            if line.sale_line_id and line.certification_id.date:
                cert = line.certification_id
                cert_id = cert._origin.id
                domain = [
                    ("sale_line_id", "=", line.sale_line_id.id),
                    ("certification_id.state", "in", list(COMMITTED_STATES)),
                ]
                if cert_id:
                    domain += [
                        ("certification_id", "!=", cert_id),
                        "|",
                        ("certification_id.date", "<", cert.date),
                        "&",
                        ("certification_id.date", "=", cert.date),
                        ("certification_id", "<", cert_id),
                    ]
                previous_amount = sum(self.search(domain).mapped("amount_period"))
            line.amount_origin = previous_amount + line._period_amount(previous_amount)
            line.amount_period = line.amount_origin - previous_amount
            line.amount_origin_net = line._net_origin_amount()

    def _net_origin_amount(self):
        """Origin amount after the money the credit notes actually returned.

        A share of the billed amount is wrong when a previous certification
        was billed at another price: the form would not match the credit note.
        """
        self.ensure_one()
        origin = self.amount_origin or 0.0
        credit = self._origin_credit_amount()
        net = origin - credit
        # A negative contract line (e.g. a BC3 baja) remains negative until
        # an effective credit note reduces its magnitude.  Do not report a
        # net origin of zero for an outstanding contractual discount.
        if (self.price_unit or 0.0) < 0:
            return min(net, 0.0)
        return max(net, 0.0)

    def _origin_credit_amount(self):
        """Excluded amount reversed on this line and the ones in its origin."""
        self.ensure_one()
        if not self.sale_line_id or not self.certification_id.date:
            return 0.0
        cert = self.certification_id
        cert_id = cert._origin.id
        domain = [
            ("sale_line_id", "=", self.sale_line_id.id),
            ("certification_id.state", "in", list(COMMITTED_STATES)),
        ]
        if cert_id:
            domain += [
                ("certification_id", "!=", cert_id),
                "|",
                ("certification_id.date", "<", cert.date),
                "&",
                ("certification_id.date", "=", cert.date),
                ("certification_id", "<", cert_id),
            ]
        credited = (self.search(domain) | self)._credited_amount()
        return sum(credited.values())

    def _credited_amount(self):
        """Excluded amount reversed, including the rounding cent.

        A rounding line has quantity 1 and must not reduce the net quantity.
        It does carry the cent the product line could not, so the net amount
        has to include it.
        """
        lines = self._without_reversed_credits(self.env["account.move.line"].search([
            ("construction_certification_line_id", "in", self.ids),
            ("move_id.state", "=", "posted"),
            ("move_id.move_type", "in", ("out_refund", "in_refund")),
            ("move_id.reversed_entry_id.move_type", "in", ("out_invoice", "in_invoice")),
            ("construction_adjustment_type", "in", (False, "rounding")),
        ]))
        credited = {}
        for line in lines:
            key = line.construction_certification_line_id.id
            # A refund of a negative invoice row is a *positive* correction
            # of its contractual base.  Use the source row's sign, not abs().
            sign = -1.0 if (line.construction_certification_line_id.price_unit or 0.0) < 0 else 1.0
            credited[key] = credited.get(key, 0.0) + sign * abs(line.price_subtotal or 0.0)
        return credited

    def _without_reversed_credits(self, lines):
        """Keep only credits still effective after all posted contra-abonos."""
        if not lines:
            return lines
        return lines.filtered(
            lambda line: line.move_id._construction_reversal_still_effective()
        )

    def _period_amount(self, previous_amount):
        """Currency amount of this period, without losing the last cent.

        ``price_subtotal / quantity`` does not round-trip. The period is the
        difference between the rounded origin share and what was already
        stored, so three certifications of a 100 budget add up to 100.
        A previous certification billed at another price is not revalued:
        this period is then just the rounded quantity times its own price.
        """
        self.ensure_one()
        currency = self.certification_id.currency_id or self.company_id.currency_id
        qty = self.qty_period or 0.0
        unit = self.price_unit or 0.0
        rounded_unit = currency.round(qty * unit) if currency else qty * unit
        sale_line = self.sale_line_id
        budget = sale_line.product_uom_qty if sale_line else 0.0
        if not sale_line or not budget or not currency:
            return rounded_unit
        if abs((sale_line.price_reduce_taxexcl or 0.0) - unit) > 0.02:
            return rounded_unit
        previous_lines = self.search([
            ("sale_line_id", "=", sale_line.id),
            ("certification_id.state", "in", list(COMMITTED_STATES)),
            ("certification_id", "!=", self.certification_id.id),
        ])
        if any(abs((previous.price_unit or 0.0) - unit) > 1e-6 for previous in previous_lines):
            return rounded_unit
        target = currency.round(sale_line.price_subtotal * self._gross_qty_origin() / budget)
        period = target - (previous_amount or 0.0)
        # Negative contractual prices (e.g. BC3 award discounts) legitimately
        # produce a negative period.  They need the origin-minus-previous
        # rounding adjustment too, especially in the last partial certificate.
        if unit >= 0 and currency.compare_amounts(period, 0.0) < 0 <= qty:
            return rounded_unit
        return period

    def _invoice_quantity_price(self):
        """Measured quantity and a unit price rounded to the product precision.

        The quantity on the invoice is the quantity that was certified. A cent
        that ``quantity × unit`` cannot represent is invoiced on its own line,
        so a later recompute of the quantity cannot multiply a lump-sum price.
        """
        self.ensure_one()
        currency = self.certification_id.currency_id or self.company_id.currency_id
        amount = self.amount_period or 0.0
        if currency:
            amount = currency.round(amount)
        qty = self.qty_period or 0.0
        if not qty:
            return 1.0, amount
        precision = self.env["decimal.precision"].precision_get("Product Price") or 2
        unit = float_round(amount / qty, precision_digits=precision)
        return qty, unit

    def _invoice_rounding_amount(self):
        """Excluded cents that the rounded unit price does not carry."""
        self.ensure_one()
        currency = self.certification_id.currency_id or self.company_id.currency_id
        amount = self.amount_period or 0.0
        if currency:
            amount = currency.round(amount)
        qty, unit = self._invoice_quantity_price()
        produced = qty * unit
        if currency:
            produced = currency.round(produced)
            residual = currency.round(amount - produced)
            if currency.is_zero(residual):
                return 0.0
            return residual
        residual = amount - produced
        return 0.0 if abs(residual) <= 0.0000001 else residual

    def _gross_qty_origin(self):
        """Origin before credit notes, for the amount share.

        ``qty_origin`` is net of posted credit notes. The share of the budget
        has to use the quantity that was certified, or a partial credit would
        underbill the next certification.
        """
        self.ensure_one()
        if not self.sale_line_id or not self.certification_id.date:
            return self.qty_period or 0.0
        cert = self.certification_id
        cert_id = cert._origin.id
        domain = [
            ("sale_line_id", "=", self.sale_line_id.id),
            ("certification_id.state", "in", list(COMMITTED_STATES)),
        ]
        if cert_id:
            domain += [
                ("certification_id", "!=", cert_id),
                "|",
                ("certification_id.date", "<", cert.date),
                "&",
                ("certification_id.date", "=", cert.date),
                ("certification_id", "<", cert_id),
            ]
        return sum(self.search(domain).mapped("qty_period")) + (self.qty_period or 0.0)

    def _company_product_taxes(self):
        """Sale taxes of the product, limited to the certification company."""
        self.ensure_one()
        product = self.product_id
        company = self.company_id
        taxes = product.taxes_id if product else self.env["account.tax"]
        if company and hasattr(taxes, "_filter_taxes_by_company"):
            taxes = taxes._filter_taxes_by_company(company)
        elif company:
            taxes = taxes.filtered(lambda tax: not tax.company_id or tax.company_id == company)
        return taxes

    def _mapped_sale_taxes(self, fiscal_position=None):
        """Taxes the invoice line must carry.

        A tax changed on the budget line is kept, including an empty set: that
        is an exemption. Otherwise the invoice uses the product taxes, mapped
        once with the fiscal position, the same way Odoo 20 fills a sale line.
        """
        self.ensure_one()
        sale_taxes = self.sale_line_id.tax_ids
        product_taxes = self._company_product_taxes()
        order_position = self.certification_id.sale_order_id.fiscal_position_id
        invoice_position = order_position if fiscal_position is None else fiscal_position
        expected = order_position.map_tax(product_taxes) if order_position else product_taxes
        # Empty is a manual change. ``bool(sale_taxes)`` used to skip it, so
        # clearing the budget VAT put the product tax back on the invoice.
        if set(sale_taxes.ids) != set(expected.ids):
            return sale_taxes
        position = invoice_position or order_position
        if position and product_taxes:
            return position.map_tax(product_taxes)
        return product_taxes

    def _invoice_line_name(self):
        self.ensure_one()
        name = self.name or self.product_id.display_name or ""
        quantity, _unit = self._invoice_quantity_price()
        if quantity == 1.0 and abs((self.qty_period or 0.0) - 1.0) > 1e-6:
            uom = self.product_uom_id.name or ""
            name = _("%(name)s (%(qty)s %(uom)s)") % {
                "name": name,
                "qty": self.qty_period,
                "uom": uom,
            }
        return name

    def _prepare_invoice_line_vals(self):
        self.ensure_one()
        # Do not set sale_line_ids. That would mark the sales order line as
        # invoiced and mix this origin invoice with the standard sales flow.
        quantity, unit = self._invoice_quantity_price()
        vals = {
            "product_id": self.product_id.id,
            "name": self._invoice_line_name(),
            "quantity": quantity,
            "price_unit": unit,
            "product_uom_id": self.product_uom_id.id,
            "tax_ids": [(6, 0, self._mapped_sale_taxes().ids)],
            "construction_certification_id": self.certification_id.id,
            "construction_certification_line_id": self.id,
        }
        distribution = self._invoice_analytic_distribution()
        if distribution:
            vals["analytic_distribution"] = distribution
        if self.product_id and hasattr(self.product_id, "_get_product_accounts"):
            account = self.product_id._get_product_accounts().get("income")
            if account:
                vals["account_id"] = account.id
        return vals

    def _prepare_rounding_line_vals(self):
        """One cent line so the certified quantity can keep a rounded unit price."""
        self.ensure_one()
        residual = self._invoice_rounding_amount()
        if not residual:
            return False
        vals = {
            "name": _("Rounding: %s") % (self.name or self.product_id.display_name or ""),
            "quantity": 1.0,
            "price_unit": residual,
            "tax_ids": [(6, 0, self._mapped_sale_taxes().ids)],
            "construction_certification_id": self.certification_id.id,
            "construction_certification_line_id": self.id,
            "construction_adjustment_type": "rounding",
        }
        distribution = self._invoice_analytic_distribution()
        if distribution:
            vals["analytic_distribution"] = distribution
        if self.product_id and hasattr(self.product_id, "_get_product_accounts"):
            account = self.product_id._get_product_accounts().get("income")
            if account:
                vals["account_id"] = account.id
        return vals

    def _recompute_open_siblings(self):
        siblings = self.search([
            ("sale_line_id", "in", self.sale_line_id.ids),
            ("id", "not in", self.ids),
            ("certification_id.state", "in", list(OPEN_STATES)),
        ])
        if siblings:
            siblings._compute_origin()
            siblings._compute_amounts()
            siblings.certification_id._compute_amounts()

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._measurement_vals(vals) for vals in vals_list]
        records = super().create(vals_list)
        records._check_editable()
        records._recompute_open_siblings()
        return records

    def _sync_measurement(self, vals):
        """Align qty and percent, and snapshot the price when the sale line changes."""
        self.ensure_one()
        vals = dict(vals)
        if vals.get("sale_line_id"):
            sale_line = self.env["sale.order.line"].browse(vals["sale_line_id"])
        else:
            sale_line = self.sale_line_id
        budget = sale_line.product_uom_qty if sale_line else 0.0
        if "sale_line_id" in vals and "price_unit" not in vals and sale_line:
            vals["price_unit"] = self._certified_price_unit(sale_line)
        if budget:
            if "qty_period" in vals and "percent_period" not in vals:
                vals["percent_period"] = (vals.get("qty_period") or 0.0) / budget
            elif "percent_period" in vals and "qty_period" not in vals:
                vals["qty_period"] = (vals.get("percent_period") or 0.0) * budget
        return vals

    def write(self, vals):
        self._check_editable()
        if {"qty_period", "percent_period", "sale_line_id"} & set(vals):
            for line in self:
                super(ConstructionCertificationLine, line).write(line._sync_measurement(vals))
            res = True
        else:
            res = super().write(vals)
        if {"qty_period", "percent_period", "sale_line_id", "certification_id", "price_unit"} & set(vals):
            self._recompute_open_siblings()
        return res

    def unlink(self):
        self._check_editable()
        sale_lines = self.sale_line_id
        certifications = self.certification_id
        res = super().unlink()
        siblings = self.search([
            ("sale_line_id", "in", sale_lines.ids),
            ("certification_id.state", "in", list(OPEN_STATES)),
        ])
        if siblings:
            siblings._compute_origin()
            siblings._compute_amounts()
            siblings.certification_id._compute_amounts()
        open_certs = certifications.filtered(lambda cert: cert.state in OPEN_STATES)
        if open_certs:
            open_certs._compute_amounts()
        return res
