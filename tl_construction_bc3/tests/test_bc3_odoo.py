# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Odoo 20 ORM integration regressions; run in a test database.

These are deliberately separate from the standalone parser test suite.
"""
import base64
import unittest

try:
    from odoo.tests import tagged
    from odoo.tests.common import TransactionCase
    from odoo.exceptions import UserError
except ImportError:  # standalone unittest execution (no Odoo installed)
    tagged = lambda *args: lambda cls: cls
    TransactionCase = unittest.TestCase
    UserError = ValueError


BC3_BUDGET = "\n".join([
    "~V|Pruebas|FIEBDC-3/2024|Tests|Budget|850|c|2|",
    "~C|ROOT##||Obra de prueba||||",
    "~C|A|u|Demoliciones|10||0|",
    "~C|B|u|Acabados|20||0|",
    "~D|ROOT##|A\\1\\5\\B\\1\\3\\|",
    "~M|ROOT\\A|1\\|5|||",
    "~M|ROOT\\B|2\\|3|||",
])


@tagged("post_install", "-at_install")
class TestBc3Odoo(TransactionCase):
    def setUp(self):
        if not hasattr(self, "env"):
            self.skipTest("Requires Odoo 20")
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "BC3 audit customer"})

    def _wizard(self, source=BC3_BUDGET, order=None):
        return self.env["bc3.import.wizard"].create({
            "filename": "test.bc3",
            "data_file": base64.b64encode(source.encode("cp850")),
            "import_mode": "budget",
            "partner_id": self.partner.id,
            "sale_order_id": order.id if order else False,
            "update_existing": False,
            "prefer_decomposition_price": False,
            "validation_mode": "strict",
        })

    def test_preview_does_not_write_and_reimport_does_not_duplicate(self):
        preview = self._wizard()
        preview.action_preview()
        self.assertFalse(self.env["sale.order"].search([
            ("partner_id", "=", self.partner.id), ("bc3_filename", "=", "test.bc3")
        ]))
        action = self._wizard().action_import()
        order = self.env["sale.order"].browse(action["res_id"])
        bc3_lines = order.order_line.filtered(lambda line: line.bc3_path)
        self.assertEqual(len(bc3_lines), 2)
        self.assertEqual(set(bc3_lines.mapped("bc3_path")), {"1", "2"})
        self.assertAlmostEqual(order.amount_untaxed, 110)
        self._wizard(order=order).action_import()
        self.assertEqual(len(order.order_line.filtered(lambda line: line.bc3_path)), 2)
        self.assertAlmostEqual(order.amount_untaxed, 110)

    def test_reimport_rejects_changed_code_at_same_tree_position(self):
        action = self._wizard().action_import()
        order = self.env["sale.order"].browse(action["res_id"])
        changed = BC3_BUDGET.replace("A\\1\\5", "B\\1\\5")
        with self.assertRaises(UserError):
            self._wizard(source=changed, order=order).action_import()

    def test_existing_ordinary_product_with_matching_sku_is_not_modified(self):
        template = self.env["product.template"].create({
            "name": "Unrelated manual product", "default_code": "A",
            "list_price": 999.0, "type": "service",
        })
        self._wizard().action_import()
        self.assertEqual(template.name, "Unrelated manual product")
        self.assertAlmostEqual(template.list_price, 999.0)
        self.assertFalse(template.bc3_code)

    def test_catalog_isolation_and_import_history(self):
        action = self._wizard().action_import()
        order = self.env["sale.order"].browse(action["res_id"])
        catalog = order.bc3_catalog_id
        self.assertTrue(catalog)
        first_product = order.order_line.filtered(lambda ln: ln.bc3_code == "A").product_id
        new_source = BC3_BUDGET.replace("~V|Pruebas|", "~V|Otra base|" )
        second = self._wizard(source=new_source).action_import()
        other_order = self.env["sale.order"].browse(second["res_id"])
        self.assertNotEqual(catalog, other_order.bc3_catalog_id)
        other_product = other_order.order_line.filtered(lambda ln: ln.bc3_code == "A").product_id
        self.assertNotEqual(first_product, other_product)
        import hashlib
        audits = self.env["bc3.import.history"].search([
            ("sale_order_id", "=", order.id)
        ])
        self.assertEqual(len(audits), 1)
        self.assertEqual(
            audits.checksum_sha256,
            hashlib.sha256(BC3_BUDGET.encode("cp850")).hexdigest(),
        )
        with self.assertRaises(UserError):
            audits.write({"name": "Should not be allowed"})

    def test_cumulative_certificate_and_zero_delta_draft_reimport(self):
        if "construction.certification" not in self.env:
            self.skipTest("Requires tl_construction_certification")
        source = "\n".join([
            "~V|Pruebas|FIEBDC-3/2024|Tests|Budget|850|c|2|",
            "~C|ROOT##||Obra de prueba||||",
            "~C|A|u|Demoliciones|10||0|",
            "~D|ROOT##|A\\1\\100\\|",
            "~M|ROOT\\A|1\\|100|||",
        ])
        action = self._wizard(source=source).action_import()
        order = self.env["sale.order"].browse(action["res_id"])
        order.action_confirm()
        sale_line = order.order_line.filtered(lambda ln: ln.bc3_code == "A")
        Cert = self.env["construction.certification"]
        CertLine = self.env["construction.certification.line"]
        first = Cert.create({"sale_order_id": order.id, "date": "2026-08-31"})
        CertLine.create({
            "certification_id": first.id,
            "sale_line_id": sale_line.id,
            "qty_period": 40,
        })
        first.action_approve()

        def cumulative(qty):
            return "\n".join([
                "~V|Pruebas|FIEBDC-3/2024|Tests|Certificate|850|c|3|2|30092026|",
                "~C|ROOT##||Obra de prueba||||",
                "~C|A|u|Demoliciones|10||0|",
                "~D|ROOT##|A\\1\\%s\\|" % qty,
                "~M|ROOT\\A|1\\|%s|||" % qty,
            ])

        self._wizard(source=cumulative(70), order=order).action_import()
        second = Cert.search([
            ("sale_order_id", "=", order.id),
            ("certification_number", "=", 2),
        ])
        self.assertEqual(len(second), 1)
        self.assertAlmostEqual(second.line_ids.qty_period, 30)
        # Reimporting the same number with origin=40 must DELETE stale 30.
        self._wizard(source=cumulative(40), order=order).action_import()
        second.invalidate_recordset()
        self.assertEqual(second.state, "draft")
        self.assertFalse(second.line_ids)

    def test_explicit_source_editions_isolate_same_code(self):
        first_wizard = self._wizard()
        first_wizard.catalog_edition = "Q1-2026"
        first_result = first_wizard.action_import()
        first = self.env["sale.order"].browse(first_result["res_id"])
        second_wizard = self._wizard()
        second_wizard.catalog_edition = "Q2-2026"
        second_result = second_wizard.action_import()
        second = self.env["sale.order"].browse(second_result["res_id"])
        self.assertNotEqual(first.bc3_catalog_id, second.bc3_catalog_id)
        self.assertEqual(first.bc3_catalog_id.edition, "Q1-2026")
        self.assertEqual(second.bc3_catalog_id.edition, "Q2-2026")
        self.assertNotEqual(
            first.order_line.filtered(lambda ln: ln.bc3_code == "A").product_id,
            second.order_line.filtered(lambda ln: ln.bc3_code == "A").product_id,
        )

    def test_coefficients_and_negative_baja_follow_origin(self):
        if "construction.certification" not in self.env:
            self.skipTest("Requires tl_construction_certification")
        budget = "\n".join([
            "~V|Pruebas|FIEBDC-3/2024|Tests|Budget|850|c|2|",
            "~K||0\\13\\6\\10\\0|",
            "~C|ROOT##||Obra de prueba||||",
            "~C|A|u|Partida|10||0|",
            "~D|ROOT##|A\\1\\100\\|",
            "~M|ROOT\\A|1\\|100|||",
        ])
        wizard = self._wizard(source=budget)
        wizard.apply_coefficients = True
        action = wizard.action_import()
        order = self.env["sale.order"].browse(action["res_id"])
        work = order.order_line.filtered(lambda row: row.bc3_code == "A")
        coeffs = order.order_line.filtered(
            lambda row: row.bc3_path and row.bc3_path.startswith("coef:")
        )
        self.assertEqual(set(coeffs.mapped("bc3_code")),
                         {"BC3-GG", "BC3-BI", "BC3-BAJA"})
        self.assertAlmostEqual(order.amount_untaxed, 1071, places=2)
        order.action_confirm()

        def certificate(qty, number, date_value):
            return "\n".join([
                "~V|Pruebas|FIEBDC-3/2024|Tests|Certificate|850|c|3|%s|%s|" % (
                    number, date_value,
                ),
                "~K||0\\13\\6\\10\\0|",
                "~C|ROOT##||Obra de prueba||||",
                "~C|A|u|Partida|10||0|",
                "~D|ROOT##|A\\1\\%s\\|" % qty,
                "~M|ROOT\\A|1\\|%s|||" % qty,
            ])

        self._wizard(source=certificate(40, 1, "31082026"), order=order).action_import()
        Cert = self.env["construction.certification"]
        first = Cert.search([
            ("sale_order_id", "=", order.id), ("certification_number", "=", 1)
        ])
        self.assertEqual(len(first.line_ids), 4)
        self.assertAlmostEqual(first.line_ids.filtered(
            lambda ln: ln.sale_line_id == work
        ).qty_period, 40)
        first.retention_percent = 0
        self.assertAlmostEqual(first.amount_to_invoice, 428.40, places=2)
        # Must invoice negative BAJA, not silently discard it.
        values = first._prepare_invoice_vals()
        product_rows = [row[2] for row in values["invoice_line_ids"]
                        if row[2].get("construction_certification_line_id")]
        self.assertEqual(len(product_rows), 4)
        self.assertTrue(any(row["price_unit"] < 0 for row in product_rows))
        first.action_approve()

        self._wizard(source=certificate(70, 2, "30092026"), order=order).action_import()
        second = Cert.search([
            ("sale_order_id", "=", order.id), ("certification_number", "=", 2)
        ])
        self.assertEqual(len(second.line_ids), 4)
        self.assertAlmostEqual(second.line_ids.filtered(
            lambda ln: ln.sale_line_id == work
        ).qty_period, 30)
        for code in ("BC3-GG", "BC3-BI", "BC3-BAJA"):
            self.assertAlmostEqual(second.line_ids.filtered(
                lambda ln, code=code: ln.sale_line_id.bc3_code == code
            ).qty_period, 0.3, places=5)
        second.retention_percent = 0
        self.assertAlmostEqual(second.amount_to_invoice, 321.30, places=2)
        self._wizard(source=certificate(70, 2, "30092026"), order=order).action_import()
        second.invalidate_recordset()
        self.assertEqual(len(second.line_ids), 4)
        self.assertAlmostEqual(second.amount_to_invoice, 321.30, places=2)

    def test_currency_mismatch_blocks_reimport(self):
        action = self._wizard().action_import()
        order = self.env["sale.order"].browse(action["res_id"])
        foreign = BC3_BUDGET + (
            "\n~K|2\\2\\2\\2\\2\\2\\2\\2\\JPY\\|0\\0\\0\\0\\0|"
        )
        with self.assertRaises(UserError):
            self._wizard(source=foreign, order=order).action_import()
