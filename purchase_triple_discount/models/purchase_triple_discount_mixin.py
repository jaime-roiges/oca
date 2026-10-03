# Copyright 2017-19 Tecnativa - David Vidal
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import functools

from odoo import api, fields, models


class TripleDiscountMixin(models.AbstractModel):
    _name = "purchase.triple.discount.mixin"
    _description = "Purchase Triple Discount Mixin"

    # Keep full precision for the aggregated discount. The visible/editable
    # values are discount1/discount2/discount3; the core discount is hidden by
    # this addon and is used by Odoo's tax/subtotal computations.
    discount = fields.Float(
        string="Total Discount (%)",
        compute="_compute_discount",
        store=True,
        readonly=True,
        digits=None,
    )
    discount1 = fields.Float(
        string="Disc. 1 (%)",
        digits="Discount",
        readonly=False,
    )
    discount2 = fields.Float(
        string="Disc. 2 (%)",
        digits="Discount",
        readonly=False,
    )
    discount3 = fields.Float(
        string="Disc. 3 (%)",
        digits="Discount",
        readonly=False,
    )

    _discount1_constraint = models.Constraint(
        "CHECK (discount1 <= 100.0)",
        "Discount 1 must be lower than 100%.",
    )
    _discount2_constraint = models.Constraint(
        "CHECK (discount2 <= 100.0)",
        "Discount 2 must be lower than 100%.",
    )
    _discount3_constraint = models.Constraint(
        "CHECK (discount3 <= 100.0)",
        "Discount 3 must be lower than 100%.",
    )

    @api.depends(lambda self: self._get_multiple_discount_field_names())
    def _compute_discount(self):
        for record in self:
            record.discount = record._get_aggregated_discount_from_values(
                {
                    fname: record[fname]
                    for fname in record._get_multiple_discount_field_names()
                }
            )

    def _get_aggregated_discount_from_values(self, values):
        discounts = [
            values.get(fname) or 0.0
            for fname in self._get_multiple_discount_field_names()
        ]
        return self._get_aggregated_multiple_discounts(discounts)

    @staticmethod
    def _get_multiple_discount_field_names():
        return ["discount1", "discount2", "discount3"]

    @staticmethod
    def _get_aggregated_multiple_discounts(discounts):
        discount_values = [1 - (discount or 0.0) / 100.0 for discount in discounts]
        return (1 - functools.reduce(lambda x, y: x * y, discount_values)) * 100
