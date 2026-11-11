import random

from dateutil.relativedelta import relativedelta

from odoo import Command, _, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DemoGenerationWizard(models.TransientModel):
    _name = "tl.demo.generation.wizard"
    _description = "Demo data generation wizard"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self) - relativedelta(months=12),
    )
    date_to = fields.Date(required=True, default=lambda self: fields.Date.context_today(self))

    sale_count = fields.Integer(string="Sales orders", default=1000, required=True)
    confirm_sales = fields.Boolean(string="Confirm sales orders", default=True)
    purchase_count = fields.Integer(string="Purchase orders", default=250, required=True)
    confirm_purchases = fields.Boolean(string="Confirm purchase orders", default=False)
    opportunity_count = fields.Integer(string="CRM opportunities", default=300, required=True)

    min_lines = fields.Integer(string="Minimum order lines", default=1, required=True)
    max_lines = fields.Integer(string="Maximum order lines", default=5, required=True)
    min_qty = fields.Integer(string="Minimum line quantity", default=1, required=True)
    max_qty = fields.Integer(string="Maximum line quantity", default=20, required=True)

    purchase_percent_min = fields.Float(
        string="Minimum purchase price (% of sale)", default=60.0, required=True
    )
    purchase_percent_max = fields.Float(
        string="Maximum purchase price (% of sale)", default=80.0, required=True
    )
    min_activities = fields.Integer(string="Minimum CRM activities", default=1, required=True)
    max_activities = fields.Integer(string="Maximum CRM activities", default=3, required=True)
    batch_size = fields.Integer(string="Documents per batch", default=20, required=True)
    random_seed = fields.Integer(string="Seed (0 for random)", default=0)

    # Separate relation tables are mandatory for the two res.partner M2M
    # fields. Define all relations explicitly to avoid future collisions.
    customer_ids = fields.Many2many(
        "res.partner", relation="tl_demo_wizard_customer_rel",
        column1="wizard_id", column2="partner_id",
        string="Customers (blank = all)",
        domain="[('customer_rank', '>', 0)]",
    )
    vendor_ids = fields.Many2many(
        "res.partner", relation="tl_demo_wizard_vendor_rel",
        column1="wizard_id", column2="partner_id",
        string="Vendors (blank = all)",
        domain="[('supplier_rank', '>', 0)]",
    )
    product_ids = fields.Many2many(
        "product.product", relation="tl_demo_wizard_product_rel",
        column1="wizard_id", column2="product_id",
        string="Products (blank = all)",
        domain="['|', ('sale_ok', '=', True), ('purchase_ok', '=', True)]",
    )
    user_ids = fields.Many2many(
        "res.users", relation="tl_demo_wizard_user_rel",
        column1="wizard_id", column2="user_id",
        string="CRM users (blank = internal users)",
        domain="[('share', '=', False), ('active', '=', True)]",
    )
    acknowledge = fields.Boolean(
        string="I confirm that this is a test database and understand the consequences",
        default=False,
    )

    def action_queue_generation(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only Settings administrators can generate demo data."))
        if self.company_id not in self.env.companies:
            raise AccessError(_("You cannot generate data for this company."))
        if not self.acknowledge:
            raise UserError(_("Confirm that this is a disposable test database."))
        if not self.date_from or not self.date_to or self.date_from > self.date_to:
            raise ValidationError(_("The date range is invalid."))

        for amount in (self.sale_count, self.purchase_count, self.opportunity_count):
            if amount < 0 or amount > 20000:
                raise ValidationError(_("Each document count must be between 0 and 20000."))
        if not (self.sale_count or self.purchase_count or self.opportunity_count):
            raise ValidationError(_("Select at least one document type."))
        if not (1 <= self.min_lines <= self.max_lines <= 30):
            raise ValidationError(_("Order lines must be between 1 and 30."))
        if not (1 <= self.min_qty <= self.max_qty <= 100000):
            raise ValidationError(_("Order quantities are not valid."))
        if not (0 < self.purchase_percent_min <= self.purchase_percent_max <= 100):
            raise ValidationError(_("Purchase percentages must satisfy 0 < min <= max <= 100."))
        if not (0 <= self.min_activities <= self.max_activities <= 10):
            raise ValidationError(_("CRM activities must be between 0 and 10 per opportunity."))
        if not (1 <= self.batch_size <= 100):
            raise ValidationError(_("Batch size must be between 1 and 100."))

        run_model = self.env["tl.demo.generation.run"]
        run_model._preflight(
            company=self.company_id,
            sale_count=self.sale_count,
            purchase_count=self.purchase_count,
            opportunity_count=self.opportunity_count,
            customer_ids=self.customer_ids.ids,
            vendor_ids=self.vendor_ids.ids,
            product_ids=self.product_ids.ids,
            user_ids=self.user_ids.ids,
        )
        run = run_model.create({
            "name": "DEMO20 / %s / %s" % (self.company_id.display_name, fields.Datetime.now()),
            "company_id": self.company_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "sale_count": self.sale_count,
            "purchase_count": self.purchase_count,
            "opportunity_count": self.opportunity_count,
            "confirm_sales": self.confirm_sales,
            "confirm_purchases": self.confirm_purchases,
            "min_lines": self.min_lines,
            "max_lines": self.max_lines,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "purchase_percent_min": self.purchase_percent_min,
            "purchase_percent_max": self.purchase_percent_max,
            "min_activities": self.min_activities,
            "max_activities": self.max_activities,
            "batch_size": self.batch_size,
            "random_seed": self.random_seed or random.SystemRandom().randint(1, 2**31 - 1),
            "customer_ids": [Command.set(self.customer_ids.ids)],
            "vendor_ids": [Command.set(self.vendor_ids.ids)],
            "product_ids": [Command.set(self.product_ids.ids)],
            "user_ids": [Command.set(self.user_ids.ids)],
        })
        run._trigger_cron()
        return {
            "type": "ir.actions.act_window",
            "name": _("Demo generation batch"),
            "res_model": "tl.demo.generation.run",
            "view_mode": "form",
            "res_id": run.id,
            "target": "current",
        }
