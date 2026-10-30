# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestConstructionAdvance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer Advance"})
        cls.sale_order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
        })

    def test_create_advance_and_apply(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 1000.0,
        })
        advance.action_confirm()
        self.assertEqual(advance.state, "confirmed")
        self.assertEqual(advance.amount_pending, 1000.0)

        # Create a simple certification to apply against
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 400.0,
        })
        self.assertEqual(certification.amount_advance_applied, 400.0)
        self.assertEqual(len(certification.application_ids), 1)
        self.assertEqual(advance.amount_pending, 600.0)

    def test_fifo_allocation_across_advances(self):
        first = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 300.0,
            "date": "2026-01-01",
        })
        second = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 200.0,
            "date": "2026-02-01",
        })
        (first | second).action_confirm()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 400.0,
        })
        applied = {app.advance_id.id: app.amount for app in certification.application_ids}
        self.assertEqual(applied[first.id], 300.0)
        self.assertEqual(applied[second.id], 100.0)
        self.assertEqual(first.amount_pending, 0.0)
        self.assertEqual(second.amount_pending, 100.0)
        self.assertEqual(first.state, "applied")
        self.assertEqual(second.state, "confirmed")

    def test_manual_application_is_not_rewritten(self):
        first = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 300.0,
            "date": "2026-01-01",
        })
        second = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 200.0,
            "date": "2026-02-01",
        })
        (first | second).action_confirm()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "application_ids": [(0, 0, {
                "advance_id": second.id,
                "amount": 150.0,
            })],
            # A total echoed next to the lines must not replace the choice.
            "amount_advance_applied": 300.0,
        })
        self.assertEqual(certification.application_ids.advance_id, second)
        self.assertEqual(certification.application_ids.amount, 150.0)
        self.assertEqual(certification.amount_advance_applied, 150.0)
        self.assertEqual(first.amount_pending, 300.0)
        self.assertEqual(second.amount_pending, 50.0)
        certification.write({"notes": "keep the manual split"})
        self.assertEqual(certification.application_ids.advance_id, second)
        self.assertEqual(certification.application_ids.amount, 150.0)

    def test_reallocation_keeps_existing_application_row(self):
        first = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 300.0,
            "date": "2026-01-01",
        })
        second = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 200.0,
            "date": "2026-02-01",
        })
        (first | second).action_confirm()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 400.0,
        })
        kept_id = certification.application_ids.filtered(
            lambda app: app.advance_id == first
        ).id
        certification.amount_advance_applied = 300.0
        self.assertEqual(certification.application_ids.advance_id, first)
        self.assertEqual(certification.application_ids.id, kept_id)
        self.assertEqual(certification.application_ids.amount, 300.0)
        self.assertEqual(second.amount_pending, 200.0)
        self.assertEqual(first.state, "applied")

    def test_later_certification_uses_only_the_pending_balance(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 1000.0,
        })
        advance.action_confirm()
        first = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 400.0,
        })
        first_app = first.application_ids
        second = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 600.0,
        })
        self.assertEqual(first.application_ids, first_app)
        self.assertEqual(first_app.amount, 400.0)
        self.assertEqual(second.application_ids.amount, 600.0)
        self.assertEqual(advance.amount_pending, 0.0)
        self.assertEqual(advance.state, "applied")
        with self.assertRaises(UserError):
            self.env["construction.certification"].create({
                "sale_order_id": self.sale_order.id,
                "amount_advance_applied": 1.0,
            })

    def test_cancel_keeps_the_application_and_frees_the_pending_amount(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 1000.0,
        })
        advance.action_confirm()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 400.0,
        })
        application = certification.application_ids
        certification.action_cancel()
        self.assertEqual(certification.state, "cancel")
        self.assertEqual(certification.application_ids, application)
        self.assertEqual(application.amount, 400.0)
        self.assertEqual(advance.amount_pending, 1000.0)
        self.assertEqual(advance.state, "confirmed")
        other = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 1000.0,
        })
        self.assertEqual(other.application_ids.amount, 1000.0)
        self.assertEqual(advance.amount_pending, 0.0)
        with self.assertRaises(UserError):
            certification.action_draft()

    def test_partial_retention_release(self):
        product = self.env["product.product"].create({
            "name": "Work",
            "type": "service",
            "list_price": 100.0,
        })
        line = self.env["sale.order.line"].create({
            "order_id": self.sale_order.id,
            "product_id": product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
        })
        self.sale_order.action_confirm()

        cert = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "retention_percent": 10.0,
            "retention_to_release": 50.0,
        })
        self.env["construction.certification.line"].create({
            "certification_id": cert.id,
            "sale_line_id": line.id,
            "qty_period": 5.0,
        })
        # to_invoice = 500, retention would be 50, but we release 50 → retention = 0
        self.assertEqual(cert.amount_to_invoice, 500.0)
        self.assertEqual(cert.amount_retention, 0.0)
        self.assertEqual(cert.amount_net_to_invoice, 500.0)

    def test_raising_the_total_keeps_the_manual_application(self):
        first = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 300.0,
            "date": "2026-01-01",
        })
        second = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 200.0,
            "date": "2026-02-01",
        })
        (first | second).action_confirm()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "application_ids": [(0, 0, {
                "advance_id": second.id,
                "amount": 150.0,
            })],
        })
        kept = certification.application_ids
        certification.amount_advance_applied = 200.0
        by_advance = {app.advance_id: app.amount for app in certification.application_ids}
        self.assertEqual(by_advance[second], 150.0)
        self.assertEqual(by_advance[first], 50.0)
        self.assertEqual(
            certification.application_ids.filtered(lambda app: app.advance_id == second),
            kept,
        )

    def test_reopening_does_not_revive_a_cancelled_advance(self):
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 1000.0,
        })
        advance.action_confirm()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "amount_advance_applied": 400.0,
        })
        certification.action_cancel()
        advance.action_cancel()
        with self.assertRaises(UserError):
            certification.action_draft()

