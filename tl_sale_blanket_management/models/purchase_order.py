# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    tl_blanket_order_id = fields.Many2one(
        "sale.blanket.order", string="Customer blanket contract", index=True,
        copy=False, check_company=True,
        domain="[('company_id', '=', company_id)]",
    )

    @api.constrains("tl_blanket_order_id", "company_id")
    def _check_tl_blanket_order(self):
        for order in self:
            contract = order.tl_blanket_order_id
            if contract and order.company_id != contract.company_id:
                raise ValidationError(_("The purchase and blanket contract must belong to the same company."))
