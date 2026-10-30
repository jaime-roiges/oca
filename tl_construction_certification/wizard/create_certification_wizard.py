# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CreateCertificationWizard(models.TransientModel):
    _name = "create.certification.wizard"
    _description = "Create Work Certification from Sales Order"

    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        required=True,
        readonly=True,
    )
    date = fields.Date(
        string="Certification Date",
        required=True,
        default=fields.Date.context_today,
    )
    import_from_progress = fields.Boolean(
        string="Import quantities from Delivery Progress (MRP)",
        default=True,
        help="If checked, period quantities will be proposed from the cumulative progress of linked manufacturing orders.",
    )

    def action_create_certification(self):
        self.ensure_one()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order_id.id,
            "date": self.date,
        })

        lines_vals = []
        CertificationLine = self.env["construction.certification.line"]
        for sol in self.sale_order_id.order_line.filtered(lambda l: not l.display_type):
            previous = CertificationLine.search([
                ("sale_line_id", "=", sol.id),
                ("certification_id.state", "in", ("approved", "invoiced")),
            ])
            # Credited quantities are available again, provided the work is
            # certified once more. Standard sale invoices use the same budget.
            already = max(
                sum(previous.mapped("qty_period"))
                - sum(previous._credited_quantity().values()), 0.0,
            )
            standard = sol._prepare_qty_invoiced().get(sol, 0.0)
            remaining_budget = max((sol.product_uom_qty or 0.0) - already - standard, 0.0)
            qty_period = 0.0
            if self.import_from_progress:
                cumulated, _percent = CertificationLine._sale_line_mrp_progress(sol)
                qty_period = max(0.0, cumulated - already - standard)
            qty_period = min(qty_period, remaining_budget)

            lines_vals.append((0, 0, {
                "sale_line_id": sol.id,
                "qty_period": qty_period,
            }))

        certification.write({"line_ids": lines_vals})

        return {
            "type": "ir.actions.act_window",
            "res_model": "construction.certification",
            "res_id": certification.id,
            "view_mode": "form",
            "target": "current",
        }
