# Copyright 2015 ADHOC SA  (http://www.adhoc.com.ar)
# Copyright 2017 - 2019 Alex Comba - Agile Business Group
# Copyright 2017 Tecnativa - David Vidal
# Copyright 2018 Simone Rubino - Agile Business Group
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Odoo 20 computes the core discount from the pricelist. This module stores the
    # exact aggregate of the three editable discounts in that core field so that
    # all standard tax/amount logic keeps using a single effective percentage.
    discount = fields.Float(
        string="Total Disc (%)",
        compute="_compute_discount",
        inverse="_inverse_discount",
        store=True,
        readonly=True,
        digits=None,
    )
    discount1 = fields.Float(
        compute="_compute_discounts",
        precompute=True,
        store=True,
        readonly=False,
        string="Disc. 1 (%)",
        digits="Discount",
        default=0.0,
    )
    discount2 = fields.Float(
        compute="_compute_discounts",
        precompute=True,
        store=True,
        readonly=False,
        string="Disc. 2 (%)",
        digits="Discount",
        default=0.0,
    )
    discount3 = fields.Float(
        compute="_compute_discounts",
        precompute=True,
        store=True,
        readonly=False,
        string="Disc. 3 (%)",
        digits="Discount",
        default=0.0,
    )
    discounting_type = fields.Selection(
        selection=[("additive", "Additive"), ("multiplicative", "Multiplicative")],
        default="multiplicative",
        required=True,
        help="Specifies whether discounts should be additive or multiplicative.\n"
        "Additive discounts are summed first and then applied.\n"
        "Multiplicative discounts are applied sequentially.\n"
        "Multiplicative discounts are default.",
    )

    _discount1_limit = models.Constraint(
        "CHECK (discount1 <= 100.0)",
        "Discount 1 must be lower or equal than 100%.",
    )
    _discount2_limit = models.Constraint(
        "CHECK (discount2 <= 100.0)",
        "Discount 2 must be lower or equal than 100%.",
    )
    _discount3_limit = models.Constraint(
        "CHECK (discount3 <= 100.0)",
        "Discount 3 must be lower or equal than 100%.",
    )

    @api.model
    def _discount_fields(self):
        return ["discount1", "discount2", "discount3"]

    def _get_final_discount(self):
        self.ensure_one()
        if self.discounting_type == "additive":
            return self._additive_discount()
        if self.discounting_type == "multiplicative":
            return self._multiplicative_discount()
        raise ValidationError(
            self.env._(
                "Sale order line %(name)s has unknown discounting type %(disc_type)s",
                name=self.name,
                disc_type=self.discounting_type,
            )
        )

    def _additive_discount(self):
        self.ensure_one()
        discount = sum(self[field] or 0.0 for field in self._discount_fields())
        return max(0.0, min(100.0, discount))

    def _multiplicative_discount(self):
        self.ensure_one()
        factor = 1.0
        for field in self._discount_fields():
            factor *= 1.0 - (self[field] or 0.0) / 100.0
        return 100.0 - factor * 100.0

    @api.depends("discount1", "discount2", "discount3", "discounting_type")
    def _compute_discount(self):
        # Combo item lines can be precomputed before their parent has been linked.
        # Defer those lines until create() has established linked_line_id.
        lines = self.filtered(lambda line: line.linked_line_id or not line.combo_item_id)
        super(SaleOrderLine, lines)._compute_discount()
        for line in lines:
            line.discount = line._get_final_discount()

    def _inverse_discount(self):
        for line in self:
            line.update({"discount1": line.discount, "discount2": 0.0, "discount3": 0.0})

    @api.depends("discount")
    def _compute_discounts(self):
        # Pull the Odoo/pricelist-computed discount into discount1. Calling the
        # parent implementation avoids recursively recalculating the aggregate.
        lines = self.filtered(lambda line: line.linked_line_id or not line.combo_item_id)
        super(SaleOrderLine, lines)._compute_discount()
        lines._inverse_discount()

    def _prepare_invoice_line(self, **kwargs):
        """Propagate the discounts while keeping sale/invoice totals identical."""
        vals = super()._prepare_invoice_line(**kwargs)
        # Sections, notes and combo headers do not carry price/discount values.
        if vals.get("display_type") != "product":
            vals.pop("discount", None)
            return vals

        # account_invoice_triple_discount computes ``discount`` from discount1/2/3,
        # so do not pass the aggregate core field in parallel.
        vals.pop("discount", None)
        if self.discounting_type == "multiplicative":
            vals.update(
                {
                    "discount1": self.discount1,
                    "discount2": self.discount2,
                    "discount3": self.discount3,
                }
            )
        else:
            # The invoice addon has no additive mode. A single equivalent discount
            # preserves the exact untaxed/tax/total amounts of the sale line.
            vals.update(
                {
                    "discount1": self.discount,
                    "discount2": 0.0,
                    "discount3": 0.0,
                }
            )
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines_to_sync = lines
        for line, vals in zip(lines, vals_list, strict=False):
            # If a triple discount was explicitly provided, keep it. Otherwise pull
            # a core/pricelist-generated discount into discount1 after create.
            if (line.discount != 0.0 or line.discount1 != 0.0) or (
                line.discount == 0.0
                and line.discount1 == 0.0
                and "discount1" in vals
                and vals["discount1"] == 0
            ):
                lines_to_sync -= line
        lines_to_sync._compute_discounts()
        return lines
