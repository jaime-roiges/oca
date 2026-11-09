# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.constrains("partner_id")
    def check_partner_id(self):
        # A delivery/billing contact of the same commercial company can use the
        # parent company's agreement, as required by normal B2B account trees.
        for order in self:
            commercial = order.partner_id.commercial_partner_id
            for line in order.order_line.filtered("blanket_order_line"):
                if line.blanket_order_line.partner_id.commercial_partner_id != commercial:
                    raise ValidationError(_("Blanket contract belongs to another customer company."))


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_eligible_bo_lines_domain(self, base_qty):
        domain = super()._get_eligible_bo_lines_domain(base_qty)
        if self.order_id.partner_id:
            commercial = self.order_id.partner_id.commercial_partner_id
            partner_ids = list(set([commercial.id, self.order_id.partner_id.id]))
            domain = [
                ("partner_id", "in", partner_ids) if item ==
                ("partner_id", "=", self.order_id.partner_id.id) else item
                for item in domain
            ]
        return domain
