import logging
import random
import traceback
from datetime import datetime, time, timedelta

from markupsafe import escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class DemoGenerationRun(models.Model):
    _name = "tl.demo.generation.run"
    _description = "Demo sales, purchase and CRM generation batch"
    _order = "id desc"

    name = fields.Char(required=True, readonly=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("done", "Done"),
            ("done_with_errors", "Done with errors"),
            ("failed", "Stopped after errors"),
            ("cancelled", "Cancelled"),
        ],
        default="queued", required=True, readonly=True, index=True,
    )
    date_from = fields.Date(required=True, readonly=True)
    date_to = fields.Date(required=True, readonly=True)
    sale_count = fields.Integer(readonly=True)
    purchase_count = fields.Integer(readonly=True)
    opportunity_count = fields.Integer(readonly=True)
    confirm_sales = fields.Boolean(readonly=True)
    confirm_purchases = fields.Boolean(readonly=True)
    min_lines = fields.Integer(readonly=True)
    max_lines = fields.Integer(readonly=True)
    min_qty = fields.Integer(readonly=True)
    max_qty = fields.Integer(readonly=True)
    purchase_percent_min = fields.Float(readonly=True)
    purchase_percent_max = fields.Float(readonly=True)
    min_activities = fields.Integer(readonly=True)
    max_activities = fields.Integer(readonly=True)
    batch_size = fields.Integer(readonly=True)
    random_seed = fields.Integer(readonly=True)

    # Each M2M field uses its own relation table. In particular, customer_ids
    # and vendor_ids both point to res.partner: an implicit relation would
    # result in the same table/columns, which Odoo 20 explicitly disallows.
    customer_ids = fields.Many2many(
        "res.partner", relation="tl_demo_run_customer_rel",
        column1="run_id", column2="partner_id",
        string="Selected customers", readonly=True,
    )
    vendor_ids = fields.Many2many(
        "res.partner", relation="tl_demo_run_vendor_rel",
        column1="run_id", column2="partner_id",
        string="Selected vendors", readonly=True,
    )
    product_ids = fields.Many2many(
        "product.product", relation="tl_demo_run_product_rel",
        column1="run_id", column2="product_id",
        string="Selected products", readonly=True,
    )
    user_ids = fields.Many2many(
        "res.users", relation="tl_demo_run_user_rel",
        column1="run_id", column2="user_id",
        string="Selected users", readonly=True,
    )

    created_sales = fields.Integer(string="Created sales", readonly=True, default=0)
    created_purchases = fields.Integer(string="Created purchases", readonly=True, default=0)
    created_opportunities = fields.Integer(string="Created opportunities", readonly=True, default=0)
    created_activities = fields.Integer(string="Created CRM activities", readonly=True, default=0)
    failed_sales = fields.Integer(string="Failed sales", readonly=True, default=0)
    failed_purchases = fields.Integer(string="Failed purchases", readonly=True, default=0)
    failed_opportunities = fields.Integer(string="Failed opportunities", readonly=True, default=0)
    error_streak = fields.Integer(readonly=True, default=0)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)
    processed_total = fields.Integer(compute="_compute_progress")
    target_total = fields.Integer(compute="_compute_progress")
    progress_percent = fields.Float(compute="_compute_progress", string="Progress (%)")

    @api.depends(
        "sale_count", "purchase_count", "opportunity_count",
        "created_sales", "created_purchases", "created_opportunities",
        "failed_sales", "failed_purchases", "failed_opportunities",
    )
    def _compute_progress(self):
        for run in self:
            run.target_total = run.sale_count + run.purchase_count + run.opportunity_count
            run.processed_total = (
                run.created_sales + run.created_purchases + run.created_opportunities
                + run.failed_sales + run.failed_purchases + run.failed_opportunities
            )
            run.progress_percent = (
                100.0 * run.processed_total / run.target_total
                if run.target_total else 0.0
            )

    @api.model
    def _candidate_ids(self, company, customer_ids=None, vendor_ids=None,
                       product_ids=None, user_ids=None):
        # Every pool is constrained to the selected company before optional IDs
        # are applied. This avoids leaking data between companies.
        company_domain = [("company_id", "in", [False, company.id])]
        products = self.env["product.product"].sudo().with_company(company)
        partners = self.env["res.partner"].sudo().with_company(company)
        users = self.env["res.users"].sudo().with_company(company)
        active_product = [("active", "=", True), ("type", "!=", "combo")] + company_domain
        if product_ids:
            active_product.append(("id", "in", product_ids))

        customer_domain = (
            [("active", "=", True), ("customer_rank", ">", 0),
             ("type", "=", "contact")] + company_domain
        )
        vendor_domain = (
            [("active", "=", True), ("supplier_rank", ">", 0),
             ("type", "=", "contact")] + company_domain
        )
        if customer_ids:
            customer_domain.append(("id", "in", customer_ids))
        if vendor_ids:
            vendor_domain.append(("id", "in", vendor_ids))
        user_domain = [
            ("active", "=", True), ("share", "=", False),
            ("company_ids", "in", [company.id]),
        ]
        if user_ids:
            user_domain.append(("id", "in", user_ids))

        return {
            "customers": partners.search(customer_domain).ids,
            "vendors": partners.search(vendor_domain).ids,
            "sale_products": products.search(active_product + [("sale_ok", "=", True)]).ids,
            "purchase_products": products.search(active_product + [("purchase_ok", "=", True)]).ids,
            "users": users.search(user_domain).ids,
        }

    @api.model
    def _preflight(self, *, company, sale_count, purchase_count,
                   opportunity_count, customer_ids=None, vendor_ids=None,
                   product_ids=None, user_ids=None):
        pools = self._candidate_ids(
            company, customer_ids, vendor_ids, product_ids, user_ids
        )
        if (sale_count or opportunity_count) and not pools["customers"]:
            raise UserError(_("There are no eligible existing customers."))
        if (sale_count or opportunity_count) and not pools["sale_products"]:
            raise UserError(_("There are no eligible sellable products."))
        if purchase_count and not pools["vendors"]:
            raise UserError(_("There are no eligible existing suppliers."))
        if purchase_count and not pools["purchase_products"]:
            raise UserError(_("There are no eligible purchasable products."))
        if opportunity_count and not pools["users"]:
            raise UserError(_("There are no eligible internal CRM users."))
        return pools

    def _get_pools(self):
        self.ensure_one()
        return self._preflight(
            company=self.company_id,
            sale_count=self.sale_count,
            purchase_count=self.purchase_count,
            opportunity_count=self.opportunity_count,
            customer_ids=self.customer_ids.ids,
            vendor_ids=self.vendor_ids.ids,
            product_ids=self.product_ids.ids,
            user_ids=self.user_ids.ids,
        )

    def _rng(self, kind, index):
        self.ensure_one()
        return random.Random("%s:%s:%s" % (self.random_seed, kind, index))

    def _random_datetime(self, rng):
        self.ensure_one()
        start = datetime.combine(self.date_from, time.min)
        end = datetime.combine(self.date_to, time(23, 59, 59))
        return start + timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))

    @api.model
    def _trigger_cron(self):
        cron = self.env.ref(
            "tl_demo_sales_generator.ir_cron_tl_demo_generation",
            raise_if_not_found=False,
        )
        if cron and cron.active:
            cron.sudo()._trigger()

    def _prepare_order_lines(self, rng, pool):
        self.ensure_one()
        count = min(rng.randint(self.min_lines, self.max_lines), len(pool))
        product_ids = rng.sample(pool, count)
        return [(product_id, rng.randint(self.min_qty, self.max_qty))
                for product_id in product_ids]

    def _create_sale(self, rng, pools):
        self.ensure_one()
        company = self.company_id
        customer_id = rng.choice(pools["customers"])
        order_date = self._random_datetime(rng)
        line_items = self._prepare_order_lines(rng, pools["sale_products"])
        lines = [
            Command.create({"product_id": product_id, "product_uom_qty": qty})
            for product_id, qty in line_items
        ]
        SaleOrder = self.env["sale.order"].sudo().with_company(company).with_context(
            tracking_disable=True, mail_create_nosubscribe=True,
            mail_notify_force_send=False,
        )
        sale = SaleOrder.create({
            "company_id": company.id,
            "partner_id": customer_id,
            "date_order": order_date,
            "origin": "DEMO20 / RUN-%s" % self.id,
            "tl_demo_generation_run_id": self.id,
            "order_line": lines,
        })
        if self.confirm_sales:
            sale.action_confirm()
            # Standard confirmation usually resets the order date to the
            # current date. Keep the fake historic date for sales reporting.
            sale.write({"date_order": order_date})
        return sale

    def _create_purchase(self, rng, pools):
        self.ensure_one()
        company = self.company_id
        vendor_id = rng.choice(pools["vendors"])
        order_date = self._random_datetime(rng)
        lines = []
        expected_prices = {}
        products = self.env["product.product"].sudo().with_company(company)
        for product_id, qty in self._prepare_order_lines(
            rng, pools["purchase_products"]
        ):
            product = products.browse(product_id)
            # Native Odoo 20 does not define uom_po_id any more.
            # Other installed addons may reintroduce it.
            purchase_uom = (
                product.uom_po_id
                if "uom_po_id" in product._fields and product.uom_po_id
                else product.uom_id
            )
            sale_price_in_purchase_uom = product.uom_id._compute_price(
                max(0.0, product.lst_price), purchase_uom
            )
            percent = rng.uniform(
                self.purchase_percent_min, self.purchase_percent_max
            )
            price = company.currency_id.round(
                sale_price_in_purchase_uom * percent / 100.0
            )
            expected_prices[product_id] = price
            planned = order_date + timedelta(days=rng.randint(2, 20))
            lines.append(Command.create({
                "product_id": product_id,
                "product_qty": qty,
                "uom_id": purchase_uom.id,
                "price_unit": price,
                "date_planned": planned,
            }))

        PurchaseOrder = self.env["purchase.order"].sudo().with_company(company).with_context(
            tracking_disable=True, mail_create_nosubscribe=True,
            mail_notify_force_send=False,
        )
        purchase = PurchaseOrder.create({
            "company_id": company.id,
            "partner_id": vendor_id,
            # Keep the order in company currency so the 60-80% comparison
            # is not invalidated by a vendor's foreign currency.
            "currency_id": company.currency_id.id,
            "date_order": order_date,
            "origin": "DEMO20 / RUN-%s" % self.id,
            "tl_demo_generation_run_id": self.id,
            "order_line": lines,
        })
        # Purchase price_unit is a writable computed field. Explicitly
        # enforce the generated price after product/vendor recomputations.
        for line in purchase.order_line.filtered(lambda line: line.product_id):
            line.write({"price_unit": expected_prices[line.product_id.id],
                        "discount": 0.0})
        if self.confirm_purchases:
            purchase.button_confirm()
            # Purchase double-validation may leave state 'to approve'.
            # Do not bypass approval rules or force the state via SQL.
            if purchase.state == "purchase":
                purchase.write({"date_approve": order_date})
            purchase.write({"date_order": order_date})
        return purchase

    def _create_opportunity(self, rng, pools):
        self.ensure_one()
        company = self.company_id
        customer_id = rng.choice(pools["customers"])
        product_id = rng.choice(pools["sale_products"])
        user_id = rng.choice(pools["users"])
        product = self.env["product.product"].sudo().with_company(company).browse(product_id)
        customer = self.env["res.partner"].sudo().browse(customer_id)
        virtual_date = self._random_datetime(rng)
        description = (
            "<p><strong>DEMO20 / RUN-%s</strong> - Synthetic CRM record.</p>"
            "<p>Customer: %s<br/>Product: %s<br/>Synthetic reference date: %s</p>"
        ) % (
            self.id, escape(customer.display_name), escape(product.display_name),
            virtual_date.date().isoformat(),
        )
        opportunity = self.env["crm.lead"].sudo().with_company(company).with_context(
            tracking_disable=True, mail_create_nosubscribe=True,
            mail_notify_force_send=False,
        ).create({
            "name": ("DEMO20 - %s / %s" % (product.display_name, customer.display_name))[:240],
            "type": "opportunity",
            "company_id": company.id,
            "partner_id": customer_id,
            "user_id": user_id,
            "expected_revenue": company.currency_id.round(
                max(0.0, product.lst_price) * rng.randint(1, 10)
            ),
            "probability": rng.randint(5, 90),
            "priority": rng.choice(["0", "1", "2", "3"]),
            "date_deadline": (virtual_date + timedelta(days=rng.randint(7, 60))).date(),
            "description": description,
            "tl_demo_product_id": product_id,
            "tl_demo_generation_run_id": self.id,
        })

        activity_type_ids = self.env["mail.activity.type"].sudo().search([
            ("active", "=", True),
            ("res_model", "in", [False, "crm.lead"]),
            ("category", "in", ["default", "phonecall"]),
        ]).ids
        if not activity_type_ids:
            todo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
            if not todo:
                raise UserError(_("No suitable CRM activity types were found."))
            activity_type_ids = [todo.id]

        activity_templates = [
            "Call about %s", "Send product proposal: %s",
            "Review requirements for %s", "Follow up on %s",
            "Discuss pricing for %s", "Arrange presentation of %s",
            "Confirm interest in %s",
        ]
        count = rng.randint(self.min_activities, self.max_activities)
        values = []
        for _index in range(count):
            summary = rng.choice(activity_templates) % product.display_name
            values.append({
                "res_model_id": self.env["ir.model"]._get_id("crm.lead"),
                "res_id": opportunity.id,
                "activity_type_id": rng.choice(activity_type_ids),
                # Activity assignees are chosen independently of lead owners.
                "user_id": rng.choice(pools["users"]),
                # Future deadlines avoid mass overdue notifications after
                # generating a year of historical sample opportunities.
                "date_deadline": fields.Date.today() + timedelta(days=rng.randint(1, 60)),
                "summary": summary[:255],
                "note": "<p>DEMO20 - generated activity for %s.</p>" % escape(product.display_name),
            })
        if values:
            self.env["mail.activity"].sudo().with_company(company).with_context(
                tracking_disable=True, mail_notify_force_send=False,
            ).create(values)
        return opportunity, count

    def _next_document(self):
        self.ensure_one()
        if self.created_sales + self.failed_sales < self.sale_count:
            return "sale", self.created_sales + self.failed_sales
        if self.created_purchases + self.failed_purchases < self.purchase_count:
            return "purchase", self.created_purchases + self.failed_purchases
        if self.created_opportunities + self.failed_opportunities < self.opportunity_count:
            return "opportunity", self.created_opportunities + self.failed_opportunities
        return None, None

    def _process_batch(self):
        self.ensure_one()
        if self.state not in ("queued", "running"):
            return 0
        if self.state == "queued":
            self.write({"state": "running", "started_at": self.started_at or fields.Datetime.now()})
        # Preflight is repeated between batches, since master data can be
        # archived or removed while a long run is in progress.
        try:
            pools = self._get_pools()
        except Exception:
            self.write({
                "state": "failed", "finished_at": fields.Datetime.now(),
                "last_error": traceback.format_exc()[-4000:],
            })
            return 0
        processed = 0
        for _item in range(self.batch_size):
            kind, index = self._next_document()
            if not kind:
                break
            rng = self._rng(kind, index)
            try:
                with self.env.cr.savepoint():
                    if kind == "sale":
                        self._create_sale(rng, pools)
                        extra = 0
                    elif kind == "purchase":
                        self._create_purchase(rng, pools)
                        extra = 0
                    else:
                        _opportunity, extra = self._create_opportunity(rng, pools)
            except Exception:
                error = traceback.format_exc()[-4000:]
                _logger.exception("DEMO20 run %s: %s document %s failed", self.id, kind, index)
                self.write({
                    "failed_%s" % ("opportunities" if kind == "opportunity" else
                                    "purchases" if kind == "purchase" else "sales"):
                    getattr(self, "failed_%s" % (
                        "opportunities" if kind == "opportunity" else
                        "purchases" if kind == "purchase" else "sales"
                    )) + 1,
                    "last_error": error,
                    "error_streak": self.error_streak + 1,
                })
            else:
                field_name = {
                    "sale": "created_sales",
                    "purchase": "created_purchases",
                    "opportunity": "created_opportunities",
                }[kind]
                values = {field_name: getattr(self, field_name) + 1, "error_streak": 0}
                if kind == "opportunity":
                    values["created_activities"] = self.created_activities + extra
                self.write(values)
            processed += 1
            if self.error_streak >= 10:
                self.write({"state": "failed", "finished_at": fields.Datetime.now()})
                break
        if self.state == "running" and not self._next_document()[0]:
            total_failures = self.failed_sales + self.failed_purchases + self.failed_opportunities
            self.write({
                "state": "done_with_errors" if total_failures else "done",
                "finished_at": fields.Datetime.now(),
            })
        return processed

    @api.model
    def _cron_process_runs(self):
        domain = [("state", "in", ["queued", "running"])]
        run = self.search(domain, order="id", limit=1)
        if run:
            # Odoo 20's lock avoids two cron workers processing one batch.
            run = run.try_lock_for_update().filtered_domain(domain)
        if not run:
            # No runnable job, or another cron worker holds its row lock.
            self.env["ir.cron"]._commit_progress(remaining=0)
            return
        count = run._process_batch()
        remaining = 0
        for active_run in self.search(domain):
            remaining += max(0, active_run.target_total - active_run.processed_total)
        self.env["ir.cron"]._commit_progress(count, remaining=remaining)

    def _check_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only Settings administrators can manage demo batches."))

    def action_process_one_batch(self):
        self.ensure_one()
        self._check_admin()
        domain = [("state", "in", ["queued", "running"])]
        run = self.try_lock_for_update().filtered_domain(domain)
        if run:
            run._process_batch()
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_cancel_generation(self):
        self._check_admin()
        for run in self.filtered(lambda r: r.state in ("queued", "running")):
            run.write({"state": "cancelled", "finished_at": fields.Datetime.now()})
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_resume_generation(self):
        self._check_admin()
        for run in self.filtered(lambda r: r.state in ("failed", "cancelled")):
            run.write({"state": "queued", "error_streak": 0, "finished_at": False})
        self._trigger_cron()
        return {"type": "ir.actions.client", "tag": "reload"}

    def _open_generated(self, model, title):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": model,
            "view_mode": "list,form",
            "domain": [("tl_demo_generation_run_id", "=", self.id)],
            "target": "current",
        }

    def action_view_sales(self):
        return self._open_generated("sale.order", _("Generated sales"))

    def action_view_purchases(self):
        return self._open_generated("purchase.order", _("Generated purchases"))

    def action_view_opportunities(self):
        return self._open_generated("crm.lead", _("Generated opportunities"))
