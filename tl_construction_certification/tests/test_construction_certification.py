# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import mark_invoiced


@tagged("post_install", "-at_install")
class TestConstructionCertification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Construction Work",
            "type": "service",
            "list_price": 100.0,
        })
        cls.sale_order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
        })
        cls.sale_line = cls.env["sale.order.line"].create({
            "order_id": cls.sale_order.id,
            "product_id": cls.product.id,
            "product_uom_qty": 10.0,
            "price_unit": 100.0,
        })
        cls.sale_order.action_confirm()

    def test_create_certification_and_amounts(self):
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "retention_percent": 5.0,
        })
        self.env["construction.certification.line"].create({
            "certification_id": certification.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 2.0,
        })
        certification.action_measure()
        certification.action_approve()

        self.assertEqual(certification.amount_certified_origin, 200.0)
        self.assertEqual(certification.amount_to_invoice, 200.0)
        self.assertEqual(certification.amount_retention, 10.0)
        self.assertEqual(certification.amount_net_to_invoice, 190.0)

    def test_origin_cumulative(self):
        cert1 = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
        })
        self.env["construction.certification.line"].create({
            "certification_id": cert1.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 3.0,
        })
        mark_invoiced(cert1)

        cert2 = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
        })
        line2 = self.env["construction.certification.line"].create({
            "certification_id": cert2.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 2.0,
        })
        self.assertEqual(line2.qty_origin, 5.0)
        self.assertEqual(cert2.amount_previously_invoiced, 300.0)
        self.assertEqual(cert2.amount_to_invoice, 200.0)

    def test_approval_persists_origin_snapshot_before_state_freeze(self):
        """SQL snapshot must be complete before Odoo recomputes approved rows."""
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id, "retention_percent": 0.0,
        })
        line = self.env["construction.certification.line"].create({
            "certification_id": cert.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 3.0,
        })
        self.assertEqual(cert.amount_to_invoice, 300.0)
        cert.action_approve()
        self.env.cr.execute(
            "SELECT qty_origin, amount_period, amount_origin "
            "FROM construction_certification_line WHERE id = %s", [line.id],
        )
        snapshot = self.env.cr.fetchone()
        self.assertEqual(snapshot, (3.0, 300.0, 300.0))
        self.assertEqual(line.amount_period, 300.0)
        self.assertEqual(cert.amount_to_invoice, 300.0)

    def test_direct_invoiced_transition_keeps_origin_snapshot(self):
        """An import may attach an existing invoice and commit in one write."""
        cert = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id, "retention_percent": 0.0,
        })
        line = self.env["construction.certification.line"].create({
            "certification_id": cert.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 2.0,
        })
        mark_invoiced(cert)
        self.env.cr.execute(
            "SELECT qty_origin, amount_period, amount_origin "
            "FROM construction_certification_line WHERE id = %s", [line.id],
        )
        self.assertEqual(self.env.cr.fetchone(), (2.0, 200.0, 200.0))
        self.assertEqual(cert.amount_to_invoice, 200.0)

    def test_same_day_origin_uses_sequence(self):
        cert1 = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "date": "2026-06-01",
        })
        self.env["construction.certification.line"].create({
            "certification_id": cert1.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 4.0,
        })
        mark_invoiced(cert1)
        cert2 = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
            "date": "2026-06-01",
        })
        line2 = self.env["construction.certification.line"].create({
            "certification_id": cert2.id,
            "sale_line_id": self.sale_line.id,
            "qty_period": 1.0,
        })
        self.assertEqual(line2.qty_origin, 5.0)
        self.assertEqual(cert2.amount_previously_invoiced, 400.0)

    def test_cannot_certify_more_than_budget(self):
        certification = self.env["construction.certification"].create({
            "sale_order_id": self.sale_order.id,
        })
        with self.assertRaises(ValidationError):
            self.env["construction.certification.line"].create({
                "certification_id": certification.id,
                "sale_line_id": self.sale_line.id,
                "qty_period": 11.0,
            })
