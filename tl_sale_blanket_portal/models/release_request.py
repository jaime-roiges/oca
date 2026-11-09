# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class SupplyReleaseRequest(models.Model):
    _name = "tl.sale.release.request"
    _description = "Customer Request Against Blanket Contract"
    _order = "id desc"
    _check_company_auto = True

    blanket_order_id = fields.Many2one(
        "sale.blanket.order", required=True, index=True,
        ondelete="restrict", check_company=True,
        domain="[('state', '=', 'open')]",
    )
    company_id = fields.Many2one("res.company", related="blanket_order_id.company_id", store=True)
    line_id = fields.Many2one("sale.blanket.order.line", required=True,
                              ondelete="restrict", check_company=True)
    partner_id = fields.Many2one("res.partner", required=True, index=True)
    quantity = fields.Float(required=True, digits="Product Unit")
    notes = fields.Text()
    state = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"),
         ("rejected", "Rejected")], default="pending", required=True,
    )
    sale_order_id = fields.Many2one("sale.order", copy=False, check_company=True,
                                    help="Optional draft order to append this contract release to.")

    @api.constrains("blanket_order_id", "line_id", "partner_id", "quantity")
    def _check_request(self):
        for row in self:
            if row.line_id.order_id != row.blanket_order_id:
                raise ValidationError(_("Request line must belong to the selected contract."))
            if (row.partner_id.commercial_partner_id
                    != row.blanket_order_id.partner_id.commercial_partner_id):
                raise ValidationError(_("Requesting customer does not match the contract customer."))
            if float_compare(row.quantity, 0, precision_digits=
                             self.env["decimal.precision"].precision_get("Product Unit")) <= 0:
                raise ValidationError(_("Requested quantity must be positive."))

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group("sales_team.group_sale_salesman"):
            raise UserError(_("Sales permissions are required."))
        contract, line = self.blanket_order_id, self.line_id
        if self.state != "pending" or contract.state != "open":
            raise UserError(_("Only pending requests for open contracts can be approved."))
        # Per-line transaction lock prevents two simultaneous approvals
        # from over-consuming the same agreement.
        self.env.cr.execute(
            "SELECT id FROM sale_blanket_order_line WHERE id = %s FOR UPDATE", [line.id]
        )
        line.invalidate_recordset(["remaining_uom_qty"])
        precision = self.env["decimal.precision"].precision_get("Product Unit")
        if float_compare(self.quantity, line.remaining_uom_qty, precision_digits=precision) > 0:
            raise UserError(_("Remaining blanket quantity is insufficient."))
        sale = self.sale_order_id
        if sale:
            if (sale.state not in ("draft", "sent")
                    or sale.company_id != contract.company_id
                    or sale.partner_id.commercial_partner_id
                       != contract.partner_id.commercial_partner_id
                    or sale.currency_id != contract.currency_id):
                raise UserError(_("Selected draft order has incompatible customer, company or currency."))
        else:
            sale = self.env["sale.order"].create({
                "partner_id": contract.partner_id.id,
                "company_id": contract.company_id.id,
                "pricelist_id": contract.pricelist_id.id,
                "payment_term_id": contract.payment_term_id.id,
                "fiscal_position_id": contract.fiscal_position_id.id,
                "origin": contract.name,
            })
        so_line = self.env["sale.order.line"].create({
            "order_id": sale.id,
            "product_id": line.product_id.id,
            "name": line.name or line.product_id.display_name,
            "product_uom_id": line.product_uom.id,
            "product_uom_qty": self.quantity,
            "price_unit": line.price_unit,
            "tax_ids": [fields.Command.set(line.taxes_id.ids)],
            "blanket_order_line": line.id,
        })
        if so_line.blanket_order_line != line:
            raise UserError(_("The contract line changed during order generation."))
        self.write({"state": "approved", "sale_order_id": sale.id})
        # Deliberately leave draft for addition of normal products and lines
        # from other agreements. OCA validates the whole order on confirmation.
        return {"type": "ir.actions.act_window", "res_model": "sale.order",
                "res_id": sale.id, "view_mode": "form"}

    def action_reject(self):
        if any(row.state != "pending" for row in self):
            raise UserError(_("Only pending requests may be rejected."))
        self.write({"state": "rejected"})
        return True
