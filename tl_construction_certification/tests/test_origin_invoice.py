# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestOriginInvoice(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure_construction_accounts(cls.env)
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer Invoice"})
        cls.product = cls.env["product.product"].create({
            "name": "Construction Service",
            "type": "service",
            "list_price": 100.0,
            "invoice_policy": "order",
        })
        cls.sale_order = cls.env["sale.order"].with_context(default_construction_retention_due_date="2030-12-31").create({
            "partner_id": cls.partner.id,
        })
        cls.sale_line = cls.env["sale.order.line"].create({
            "order_id": cls.sale_order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
        })
        cls.sale_order.action_confirm()

    def test_create_origin_invoice(self):
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "retention_percent": 5.0,
        })
        self.env["construction.certification.line"].create({
            "certification_id": certification.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 4.0,
        })
        certification.action_measure()
        certification.action_approve()

        # Create the invoice
        action = certification.action_create_invoice()
        self.assertTrue(certification.invoice_id)
        self.assertEqual(certification.state, "invoiced")
        invoice = certification.invoice_id
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertIn("Certification", invoice.narration or "")
        self.assertAlmostEqual(invoice.amount_untaxed, 380.0, places=2)  # 400 - 5%

    def test_origin_invoice_with_advance_and_partial_retention(self):
        # Create advance
        advance = self.env["construction.advance"].create({
            "sale_order_id": self.sale_order.id,
            "amount": 100.0,
        })
        advance.action_confirm()
        advance.action_create_invoice()
        advance.invoice_id.action_post()

        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "retention_percent": 10.0,
            "retention_to_release": 20.0,
            "amount_advance_applied": 50.0,
        })
        self.env["construction.certification.line"].create({
            "certification_id": certification.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 5.0,
        })
        certification.action_measure()
        certification.action_approve()
        certification.action_create_invoice()

        invoice = certification.invoice_id
        self.assertTrue(invoice)
        # to_invoice = 500
        # retention = max(0, 50 - 20) = 30
        # net = 470
        # final = 470 - 50 = 420
        self.assertAlmostEqual(certification.amount_final_to_invoice, 420.0, places=2)
        self.assertIn("Advance Applied", invoice.narration or "")
        deducted = invoice.invoice_line_ids.filtered(
            "construction_advance_application_id"
        )
        self.assertEqual(len(deducted), 1)
        self.assertEqual(
            deducted.construction_advance_application_id,
            certification.application_ids,
        )
        self.assertAlmostEqual(deducted.price_unit, -50.0, places=2)

    def test_origin_invoice_deducts_each_application(self):
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
        for advance in first | second:
            advance.action_create_invoice()
            advance.invoice_id.action_post()
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "retention_percent": 0.0,
            "amount_advance_applied": 400.0,
        })
        self.env["construction.certification.line"].create({
            "certification_id": certification.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 5.0,
        })
        certification.action_measure()
        certification.action_approve()
        certification.action_create_invoice()
        invoice = certification.invoice_id
        deducted = invoice.invoice_line_ids.filtered(
            "construction_advance_application_id"
        )
        self.assertEqual(len(deducted), 2)
        by_advance = {
            line.construction_advance_application_id.advance_id.id: line.price_unit
            for line in deducted
        }
        self.assertAlmostEqual(by_advance[first.id], -300.0, places=2)
        self.assertAlmostEqual(by_advance[second.id], -100.0, places=2)
        self.assertEqual(
            set(deducted.mapped("construction_advance_application_id").ids),
            set(certification.application_ids.ids),
        )
        self.assertAlmostEqual(invoice.amount_untaxed, 100.0, places=2)
