# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    _bc3_order_position_uniq = models.Constraint(
        "UNIQUE(order_id, bc3_path)",
        "Only one sale line per BC3 tree position is permitted in an order.",
    )

    bc3_code = fields.Char(string="BC3 Code", index=True)
    bc3_path = fields.Char(
        string="BC3 Tree Position", index=True, copy=False,
        help="Stable FIEBDC hierarchical POSICION, e.g. 2.1.3. "
             "Distinguishes repeated concept codes within an order.",
    )
    bc3_measurement_data = fields.Json(
        string="BC3 Measurement Detail", copy=False,
        help="Original ~M/~N dimensions, comments and BIM references.",
    )
    bc3_unit = fields.Char(string="BC3 Unit")
    bc3_label = fields.Char(
        string="BC3 Label",
        help="Measurement label (etiqueta) from the ~M record.",
    )
    bc3_factor = fields.Float(string="BC3 Factor", digits="Product Unit of Measure")
    bc3_yield = fields.Float(string="BC3 Yield", digits="Product Unit of Measure")
    bc3_measured_qty = fields.Float(
        string="BC3 Measured Qty",
        digits="Product Unit of Measure",
        copy=False,
        help="Quantity taken from the BC3 measurement. On a certification file "
        "this is the quantity to date, which can be lower than the contract quantity.",
    )
    bc3_is_measured = fields.Boolean(string="BC3 Has Measurement", copy=False)
