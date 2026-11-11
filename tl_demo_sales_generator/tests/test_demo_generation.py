from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDemoGeneration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Synthetic Sales Customer", "customer_rank": 1,
        })
        cls.vendor = cls.env["res.partner"].create({
            "name": "Synthetic Purchase Vendor", "supplier_rank": 1,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Synthetic Test Product", "list_price": 100.0,
            "sale_ok": True, "purchase_ok": True, "type": "consu",
        })
        cls.company = cls.env.company

    def _create_run(self, **values):
        base = {
            "name": "DEMO20 test batch",
            "company_id": self.company.id,
            "date_from": fields.Date.today() - timedelta(days=100),
            "date_to": fields.Date.today(),
            "sale_count": 2,
            "purchase_count": 2,
            "opportunity_count": 2,
            "confirm_sales": False,
            "confirm_purchases": False,
            "min_lines": 1,
            "max_lines": 1,
            "min_qty": 1,
            "max_qty": 3,
            "purchase_percent_min": 60,
            "purchase_percent_max": 80,
            "min_activities": 2,
            "max_activities": 2,
            "batch_size": 10,
            "random_seed": 12345,
            "customer_ids": [Command.set(self.customer.ids)],
            "vendor_ids": [Command.set(self.vendor.ids)],
            "product_ids": [Command.set(self.product.ids)],
            "user_ids": [Command.set(self.env.user.ids)],
        }
        base.update(values)
        return self.env["tl.demo.generation.run"].create(base)

    def test_odoo20_ir_access_permissions(self):
        access = self.env["ir.access"].sudo()
        admin_group = self.env.ref("base.group_system")
        for model_name, expected_operations in (
            ("tl.demo.generation.run", "cru"),
            ("tl.demo.generation.wizard", "crud"),
        ):
            grants = access.search([
                ("model_id.model", "=", model_name),
                ("group_id", "=", admin_group.id),
            ])
            self.assertIn(
                expected_operations,
                grants.mapped("operation"),
                "Odoo 20 ir.access rights are missing for %s" % model_name,
            )

    def test_filter_many2many_relations_are_independent(self):
        for model_name in ("tl.demo.generation.run", "tl.demo.generation.wizard"):
            model = self.env[model_name]
            fields_to_check = (
                model._fields["customer_ids"], model._fields["vendor_ids"],
                model._fields["product_ids"], model._fields["user_ids"],
            )
            relations = [(field.relation, field.column1, field.column2)
                         for field in fields_to_check]
            self.assertEqual(len(set(relations)), len(relations))
            self.assertTrue(all(rel[0] for rel in relations))

    def test_run_creates_sales_purchases_crm_and_activities(self):
        run = self._create_run()
        processed = run._process_batch()
        self.assertEqual(processed, 6)
        self.assertEqual(run.state, "done", run.last_error or "")
        self.assertEqual(run.created_sales, 2)
        self.assertEqual(run.created_purchases, 2)
        self.assertEqual(run.created_opportunities, 2)
        self.assertEqual(run.created_activities, 4)
        self.assertEqual(run.progress_percent, 100.0)

        sales = self.env["sale.order"].search([
            ("tl_demo_generation_run_id", "=", run.id)
        ])
        self.assertEqual(len(sales), 2)
        self.assertTrue(all(order.state == "draft" for order in sales))
        self.assertTrue(all(order.partner_id == self.customer for order in sales))

        purchases = self.env["purchase.order"].search([
            ("tl_demo_generation_run_id", "=", run.id)
        ])
        self.assertEqual(len(purchases), 2)
        for order in purchases:
            self.assertEqual(order.partner_id, self.vendor)
            self.assertEqual(order.state, "draft")
            self.assertEqual(order.currency_id, self.company.currency_id)
            for line in order.order_line:
                self.assertGreaterEqual(line.price_unit, 59.99)
                self.assertLessEqual(line.price_unit, 80.01)

        opportunities = self.env["crm.lead"].search([
            ("tl_demo_generation_run_id", "=", run.id)
        ])
        self.assertEqual(len(opportunities), 2)
        self.assertTrue(all(lead.partner_id == self.customer for lead in opportunities))
        self.assertTrue(all(lead.tl_demo_product_id == self.product for lead in opportunities))
        self.assertTrue(all(lead.type == "opportunity" for lead in opportunities))
        for opportunity in opportunities:
            activities = self.env["mail.activity"].search([
                ("res_model", "=", "crm.lead"),
                ("res_id", "=", opportunity.id),
            ])
            self.assertEqual(len(activities), 2)
            self.assertTrue(all(a.user_id == self.env.user for a in activities))

    def test_zero_counts_and_cancel_resume(self):
        run = self._create_run(
            sale_count=0, purchase_count=1, opportunity_count=0,
            batch_size=1,
        )
        self.assertEqual(run._process_batch(), 1)
        self.assertEqual(run.state, "done", run.last_error or "")
        self.assertEqual(run.created_purchases, 1)
        self.assertFalse(run.created_sales)
        self.assertFalse(run.created_opportunities)
