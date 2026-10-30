# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.tools import float_round


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    construction_certification_id = fields.Many2one(
        comodel_name="construction.certification",
        string="Work Certification",
        ondelete="set null",
        index=True,
        copy=False,
    )
    construction_certification_line_id = fields.Many2one(
        comodel_name="construction.certification.line",
        string="Certification Line",
        ondelete="set null",
        index=True,
        copy=False,
    )
    construction_advance_id = fields.Many2one(
        comodel_name="construction.advance",
        string="Construction Advance",
        ondelete="set null",
        index=True,
        copy=False,
    )
    construction_advance_application_id = fields.Many2one(
        comodel_name="construction.advance.application",
        string="Advance Application",
        ondelete="set null",
        index=True,
        copy=False,
        help="Advance application deducted by this invoice line.",
    )
    construction_adjustment_type = fields.Selection(
        selection=[
            ("retention", "Guarantee Retention"),
            ("retention_release", "Retention Released"),
            ("advance", "Advance Applied"),
            ("advance_invoice", "Advance Invoice"),
            ("rounding", "Rounding"),
        ],
        string="Construction Adjustment",
        copy=False,
    )
    # Survives a recompute of price_unit. The tax engine can leave the base a
    # cent off; that cent is stored here so the next compute keeps it.
    construction_price_adjust = fields.Float(
        string="Construction Price Adjustment",
        digits="Product Price",
        copy=True,
        default=0.0,
    )

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if not self.env.context.get("construction_keep_links"):
            return vals_list
        for line, vals in zip(self, vals_list):
            vals.update({
                "construction_certification_id": line.construction_certification_id.id,
                "construction_certification_line_id": line.construction_certification_line_id.id,
                "construction_advance_id": line.construction_advance_id.id,
                "construction_advance_application_id": line.construction_advance_application_id.id,
                "construction_adjustment_type": line.construction_adjustment_type,
                "price_unit": line.price_unit,
                "quantity": line.quantity,
                "discount": line.discount,
                "account_id": line.account_id.id,
                "tax_ids": [(6, 0, line.tax_ids.ids)],
                "name": line.name,
                "construction_price_adjust": line.construction_price_adjust,
            })
            if "analytic_distribution" in line._fields and line.analytic_distribution:
                vals["analytic_distribution"] = line.analytic_distribution
        return vals_list

    def _construction_is_reversal(self):
        """A credit note of a construction invoice.

        ``move_type == out_refund`` is not enough: a manual credit note is
        also a refund, and freezing it would keep an empty price.
        """
        return self.filtered(lambda line: line.move_id.reversed_entry_id)

    def _kept_value(self, field_name):
        """Value already written, without reading a field under computation.

        ``line.price_unit = line.price_unit`` inside ``_compute_price_unit``
        recurses when the cache was invalidated. A copied credit note has the
        value in cache from the create vals, or in SQL once it is stored.
        """
        self.ensure_one()
        field = self._fields[field_name]
        if self.env.cache.contains(self, field):
            value = self.env.cache.get(self, field)
            if field.type == "many2one" and value and not isinstance(value, int):
                return value.id
            if field.type == "many2many" and value and not isinstance(value, (list, tuple)):
                return value.ids
            return value
        if not self.id:
            return None
        if field.type == "many2many":
            self.env.cr.execute(
                'SELECT "%s" FROM "%s" WHERE "%s" = %%s' % (
                    field.column2, field.relation, field.column1,
                ),
                [self.id],
            )
            return [row[0] for row in self.env.cr.fetchall()]
        self.env.cr.execute(
            'SELECT "%s" FROM account_move_line WHERE id = %%s' % field_name,
            [self.id],
        )
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _assign_kept(self, field_name):
        for line in self:
            value = line._kept_value(field_name)
            field = line._fields[field_name]
            if value is None:
                value = False if field.type in ("many2one", "many2many") else 0.0
            if field.type == "many2one":
                line[field_name] = self.env[field.comodel_name].browse(value or False)
            elif field.type == "many2many":
                line[field_name] = self.env[field.comodel_name].browse(value or [])
            else:
                line[field_name] = value

    def _construction_adjustment_lines(self):
        return self.filtered(
            lambda line: line.construction_adjustment_type not in (False, "rounding")
            or line.construction_advance_application_id
        )

    def _construction_rounding_lines(self):
        return self.filtered(lambda line: line.construction_adjustment_type == "rounding")

    def _construction_product_lines(self):
        return self.filtered(
            lambda line: line.construction_certification_line_id and line.construction_adjustment_type != "rounding"
        )

    def _construction_protected_lines(self):
        return self._construction_adjustment_lines() | self._construction_product_lines() | self._construction_rounding_lines()

    def _restore_posted_column(self, field_name):
        """Keep the value already posted.

        A module update recomputes stored fields. Recomputing a posted
        construction line would change an entry that was already billed.
        """
        posted = self.filtered(lambda line: line.parent_state == "posted" and line.id)
        if not posted:
            return posted
        field = self._fields[field_name]
        ids = tuple(posted.ids)
        if field.type == "many2many":
            self.env.cr.execute(
                'SELECT "%s", "%s" FROM "%s" WHERE "%s" IN %%s' % (
                    field.column1, field.column2, field.relation, field.column1,
                ),
                [ids],
            )
            grouped = {}
            for line_id, other_id in self.env.cr.fetchall():
                grouped.setdefault(line_id, []).append(other_id)
            comodel = self.env[field.comodel_name]
            for line in posted:
                line[field_name] = comodel.browse(grouped.get(line.id, []))
            return posted
        self.env.cr.execute(
            'SELECT id, "%s" FROM account_move_line WHERE id IN %%s' % field_name,
            [ids],
        )
        values = dict(self.env.cr.fetchall())
        if field.type == "many2one":
            comodel = self.env[field.comodel_name]
            for line in posted:
                line[field_name] = comodel.browse(values.get(line.id) or False)
        else:
            for line in posted:
                value = values.get(line.id)
                if value is None and field.type in ("float", "monetary", "integer"):
                    value = 0.0
                line[field_name] = value
        return posted

    @api.depends(
        "display_type",
        "construction_certification_line_id",
        "construction_certification_line_id.qty_period",
        "construction_adjustment_type",
    )
    def _compute_quantity(self):
        """Odoo 20 recomputes quantity from the display type.

        A certification line has to keep the measured quantity. Leaving it to
        the standard compute turns a non-divisible price into quantity 1, and
        a later recompute multiplies the lump sum.
        """
        protected = self._construction_protected_lines()
        posted = protected._restore_posted_column("quantity")
        super(AccountMoveLine, self - protected)._compute_quantity()
        open_lines = protected - posted
        kept = open_lines if self.env.context.get("construction_keep_links") else open_lines._construction_is_reversal()
        if kept:
            kept._assign_kept("quantity")
        open_lines -= kept
        for line in open_lines._construction_product_lines():
            quantity, _unit = line.construction_certification_line_id._invoice_quantity_price()
            line.quantity = quantity or 1.0
        for line in open_lines._construction_rounding_lines() | open_lines._construction_adjustment_lines():
            line.quantity = 1.0

    @api.model
    def _flatten_construction_taxes(self, taxes):
        """Replace tax groups by the taxes Odoo 20 actually computes."""
        flat = self.env["account.tax"]
        pending = taxes
        seen = set()
        while pending:
            tax = pending[:1]
            pending -= tax
            if not tax or tax.id in seen:
                continue
            seen.add(tax.id)
            children = tax.children_tax_ids if "children_tax_ids" in tax._fields else self.env["account.tax"]
            if tax.amount_type == "group" and children:
                pending |= children
            else:
                flat |= tax
        return flat

    @api.model
    def _included_tax_rate(self, taxes):
        """Percent rate when Odoo 20 treats the price as already taxed.

        ``None`` means the price is excluded. ``False`` means the taxes cannot
        be converted (a fixed amount, or included mixed with excluded).
        """
        if not taxes:
            return None
        flat = self._flatten_construction_taxes(taxes)
        group_forced = taxes.filtered(
            lambda tax: tax.amount_type == "group" and getattr(tax, "price_include_override", None) == "tax_included"
        )
        forced = flat.filtered(lambda tax: getattr(tax, "price_include_override", None) == "tax_included")
        if group_forced:
            forced = flat
        if not forced:
            return None
        if len(forced) != len(flat) or any(tax.amount_type != "percent" for tax in flat):
            return False
        return sum(flat.mapped("amount"))

    @api.depends(
        "product_id",
        "display_type",
        "construction_adjustment_type",
        "construction_advance_id",
        "construction_advance_application_id",
        "construction_certification_line_id",
        "construction_certification_id",
    )
    def _compute_account_id(self):
        """Odoo 20 drops a product-less invoice line onto the journal income account.

        The standard method has no dependencies: the product inverse triggers it.
        Declaring ``product_id`` here keeps that path when this module is
        installed, so a normal invoice still changes its income account.
        Retention and advances stay on the company liability or asset account.
        """
        protected = self._construction_protected_lines()
        posted = protected._restore_posted_column("account_id")
        super(AccountMoveLine, self - protected)._compute_account_id()
        open_lines = protected - posted
        kept = open_lines if self.env.context.get("construction_keep_links") else open_lines._construction_is_reversal()
        if kept:
            kept._assign_kept("account_id")
        open_lines -= kept
        for line in open_lines._construction_rounding_lines():
            source = line.construction_certification_line_id
            account = False
            if source.product_id and hasattr(source.product_id, "_get_product_accounts"):
                account = source.product_id._get_product_accounts().get("income")
            if account:
                line.account_id = account
        for line in open_lines._construction_adjustment_lines():
            company = line.move_id.company_id or line.company_id
            if line.construction_adjustment_type in ("advance", "advance_invoice") or line.construction_advance_application_id:
                account = company.construction_advance_account_id
            else:
                account = company.construction_retention_account_id
            if account:
                line.account_id = account

    def _construction_unit_for_document(self, amount, taxes):
        """Turn an excluded base into the price Odoo 20 will actually tax.

        A tax with ``price_include_override = tax_included`` ignores
        ``document_tax_mode`` and treats ``price_unit`` as tax included.
        The gross price is not rounded here: rounding it first makes the
        extracted base differ by a cent and the invoice is rejected.
        """
        rate = self._included_tax_rate(taxes)
        if not rate:
            return amount
        return amount * (1.0 + rate / 100.0)

    def _apply_construction_price(self):
        if self.env.context.get("construction_applying_price"):
            return
        lines = self.with_context(construction_applying_price=True)
        for line in lines._construction_product_lines():
            _quantity, unit = line.construction_certification_line_id._invoice_quantity_price()
            line.price_unit = line._construction_unit_for_document(unit, line.tax_ids) + (
                line.construction_price_adjust or 0.0
            )
        for line in lines._construction_rounding_lines():
            source = line.construction_certification_line_id
            line.price_unit = line._construction_unit_for_document(
                source._invoice_rounding_amount(), line.tax_ids
            ) + (line.construction_price_adjust or 0.0)
        for line in lines._construction_adjustment_lines():
            if line.construction_advance_application_id:
                amount = -line.construction_advance_application_id.amount
            elif line.construction_adjustment_type == "advance_invoice" and line.construction_advance_id:
                amount = line.construction_advance_id.amount
            elif line.construction_adjustment_type == "retention" and line.construction_certification_id:
                amount = -(line.construction_certification_id.amount_retention or 0.0)
            elif line.construction_adjustment_type == "retention_release" and line.construction_certification_id:
                amount = line.construction_certification_id.retention_to_release or 0.0
            else:
                amount = line.price_unit
            line.price_unit = line._construction_unit_for_document(amount, line.tax_ids) + (
                line.construction_price_adjust or 0.0
            )

    @api.depends(
        "product_id",
        "product_uom_id",
        "construction_certification_line_id",
        "construction_certification_line_id.amount_period",
        "construction_certification_line_id.qty_period",
        "construction_advance_application_id",
        "construction_advance_application_id.amount",
        "construction_advance_id",
        "construction_advance_id.amount",
        "construction_adjustment_type",
        "construction_certification_id",
        "construction_certification_id.amount_retention",
        "construction_certification_id.retention_to_release",
        "construction_price_adjust",
    )
    def _compute_price_unit(self):
        """The certification price is a snapshot. Do not replace it with the product price.

        ``tax_ids`` is not a dependency. Odoo 20 only depends on the product,
        and adding the tax here would reset the price of every customer invoice
        when its tax changes.
        """
        protected = self._construction_protected_lines()
        posted = protected._restore_posted_column("price_unit")
        super(AccountMoveLine, self - protected)._compute_price_unit()
        open_lines = protected - posted
        kept = open_lines if self.env.context.get("construction_keep_links") else open_lines._construction_is_reversal()
        if kept:
            kept._assign_kept("price_unit")
        open_lines -= kept
        open_lines._apply_construction_price()

    def _mapped_construction_taxes(self, source, fiscal_position):
        return source._mapped_sale_taxes(fiscal_position)

    @api.depends(
        "product_id",
        "construction_certification_line_id",
        "construction_certification_line_id.sale_line_id",
        "construction_certification_line_id.sale_line_id.tax_ids",
        "construction_advance_id",
        "construction_advance_id.tax_ids",
        "construction_advance_application_id",
        "construction_adjustment_type",
    )
    def _compute_tax_ids(self):
        """VAT follows the budget line, mapped by the invoice fiscal position.

        Dependencies are Odoo 20's (``product_id``) plus construction fields.
        ``product_id.taxes_id`` and ``move_id.fiscal_position_id`` are not
        here: both would recompute every customer invoice. A product tax
        change is applied to open construction lines from ``product.template``.
        A fiscal position change is applied from ``account.move.write``.

        Retention stays outside the tax base. An advance keeps the taxes of
        its posted invoice. A credit note keeps the taxes that were posted.
        """
        protected = self._construction_protected_lines()
        posted = protected._restore_posted_column("tax_ids")
        super(AccountMoveLine, self - protected)._compute_tax_ids()
        open_lines = protected - posted
        kept = open_lines if self.env.context.get("construction_keep_links") else open_lines._construction_is_reversal()
        if kept:
            kept._assign_kept("tax_ids")
        open_lines -= kept
        open_lines = self - posted - kept
        for line in open_lines._construction_product_lines() | open_lines._construction_rounding_lines():
            source = line.construction_certification_line_id
            line.tax_ids = line._mapped_construction_taxes(source, line.move_id.fiscal_position_id)
        for line in open_lines._construction_adjustment_lines():
            advance = line.construction_advance_id
            if line.construction_advance_application_id:
                advance = line.construction_advance_application_id.advance_id
            if advance and line.construction_adjustment_type == "advance_invoice":
                line.tax_ids = advance.tax_ids
            elif advance and line.construction_advance_application_id:
                line.tax_ids = advance._taxes_charged()
            else:
                line.tax_ids = False
        # Schedule the price compute. Do not assign price_unit from here:
        # it is another computed field, and writing it from this one is what
        # doubled the cent. The price compute reads the taxes just set.
        protected_open = open_lines._construction_protected_lines()
        if protected_open:
            self.env.add_to_compute(self._fields["price_unit"], protected_open)

    @api.depends("product_id", "move_id.ref", "move_id.payment_reference")
    def _compute_name(self):
        protected = self._construction_protected_lines()
        posted = protected._restore_posted_column("name")
        super(AccountMoveLine, self - protected)._compute_name()
        open_lines = protected - posted
        kept = open_lines if self.env.context.get("construction_keep_links") else open_lines._construction_is_reversal()
        if kept:
            kept._assign_kept("name")
        open_lines -= kept
        open_lines = self - posted - kept
        for line in open_lines._construction_product_lines():
            line.name = line.construction_certification_line_id._invoice_line_name()
        for line in open_lines._construction_rounding_lines():
            source = line.construction_certification_line_id
            line.name = _("Rounding: %s") % (source.name or source.product_id.display_name or "")
        for line in open_lines._construction_adjustment_lines():
            cert = line.construction_certification_id
            if line.construction_adjustment_type == "retention" and cert:
                line.name = _("Guarantee Retention (%s%%)") % cert.retention_percent
            elif line.construction_adjustment_type == "retention_release":
                line.name = _("Retention Released")
            elif line.construction_advance_application_id:
                line.name = _("Advance applied: %s") % line.construction_advance_application_id.advance_id.display_name
            elif line.construction_adjustment_type == "advance_invoice" and line.construction_advance_id:
                line.name = _("Advance - %s") % line.construction_advance_id.name

    def _force_construction_invoice_values(self):
        """Re-apply certification values after the standard Odoo 20 computes.

        A credit note is built with ``construction_keep_links`` and must keep
        the price, taxes and account that were posted, not a fresh calculation.
        """
        if self.env.context.get("construction_keep_links"):
            return
        protected = self._construction_protected_lines() - self._construction_is_reversal()
        if not protected:
            return
        protected._compute_account_id()
        protected._compute_tax_ids()
        protected._compute_price_unit()
        protected._compute_name()
        for line in protected:
            if line.construction_adjustment_type in ("advance", "advance_invoice", "retention", "retention_release"):
                distribution = line.construction_certification_id._header_analytic_distribution() if line.construction_certification_id else False
                if not distribution and line.construction_advance_id:
                    distribution = line.construction_advance_id._advance_analytic_distribution()
            elif line.construction_certification_line_id:
                distribution = line.construction_certification_line_id._invoice_analytic_distribution()
            else:
                distribution = False
            if distribution and "analytic_distribution" in line._fields:
                line.analytic_distribution = distribution

    def _refresh_open_construction_origins(self):
        """Refresh open certifications when a credit note is written or posted.

        ``_compute_origin`` depends on this line's own invoice lines. A later
        certification depends on a previous line's credit note, so the write
        has to reach the open siblings.
        """
        cert_lines = self.mapped("construction_certification_line_id")
        if cert_lines:
            # Includes invoiced lines, so their net origin moves.
            cert_lines._compute_origin()
            cert_lines._compute_amounts()
            cert_lines.certification_id._compute_amounts()
            cert_lines._recompute_open_siblings()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._force_construction_invoice_values()
        lines.filtered(lambda line: line.move_id.reversed_entry_id)._refresh_open_construction_origins()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {"quantity", "construction_certification_line_id"} & set(vals):
            self.filtered(
                lambda line: line.move_id.reversed_entry_id
            )._refresh_open_construction_origins()
        return res
