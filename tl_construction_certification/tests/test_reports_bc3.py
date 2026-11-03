# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.binary import BinaryBytes, BinaryValue
from odoo.addons.tl_construction_bc3.lib.bc3_parser import parse_bc3

BUDGET = "\n".join([
    "~V|Test|FIEBDC-3/2024|Tests|Budget|UTF-8|c|2|",
    "~C|ROOT##||Obra||||", "~C|A|u|Partida uno|10||0|",
    "~C|B|u|Partida dos|20||0|", "~D|ROOT##|A\\1\\5\\B\\1\\3\\|",
    "~M|ROOT\\A|1\\|5|||", "~M|ROOT\\B|2\\|3|||",
])


@tagged('post_install', '-at_install')
class TestReportsAndBc3Export(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Cliente BC3'})
        wizard = self.env['bc3.import.wizard'].create({
            'filename': 'presupuesto.bc3', 'data_file': BinaryBytes(BUDGET.encode()),
            'import_mode': 'budget', 'partner_id': self.partner.id,
            'update_existing': False, 'prefer_decomposition_price': False,
            'validation_mode': 'strict',
        })
        self.order = self.env['sale.order'].browse(wizard.action_import()['res_id'])
        self.order.action_confirm()
        self.sale_a = self.order.order_line.filtered(lambda line: line.bc3_code == 'A')
        self.sale_b = self.order.order_line.filtered(lambda line: line.bc3_code == 'B')

    def _cert(self, date, line, qty):
        cert = self.env['construction.certification'].create({
            'sale_order_id': self.order.id, 'date': date, 'retention_percent': 0,
        })
        self.env['construction.certification.line'].create({
            'certification_id': cert.id, 'sale_line_id': line.id, 'qty_period': qty,
        })
        cert.action_measure()
        cert.action_approve()
        return cert

    def test_report_keeps_previous_items_and_export_is_cumulative(self):
        self._cert('2026-06-01', self.sale_a, 2)
        cert = self._cert('2026-07-01', self.sale_b, 1)
        rows = [row for row in cert._report_measurement_rows() if not row['section']]
        a, b = (next(row for row in rows if row['reference'] == code) for code in ('A', 'B'))
        self.assertEqual((a['origin_qty'], a['previous_qty'], a['period_qty']), (2, 2, 0))
        self.assertEqual((b['origin_qty'], b['previous_qty'], b['period_qty']), (1, 0, 1))
        report = self.env.ref('tl_construction_certification.action_report_construction_certification')
        html, _ = self.env['ir.actions.report']._render_qweb_html(report.id, cert.ids)
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('Partida uno', html)
        self.assertIn('Partida dos', html)
        result = cert.action_export_bc3()
        attachment_id = int(result['url'].split('/')[3].split('?')[0])
        attachment = self.env['ir.attachment'].browse(attachment_id)
        self.assertEqual(attachment.res_model, cert._name)
        self.assertEqual(attachment.res_id, cert.id)
        self.assertTrue(attachment.name.endswith('#certificacion002.bc3'))
        self.assertIsInstance(attachment.datas, BinaryValue)
        doc = parse_bc3(attachment.datas.content, strict=True)
        self.assertEqual(doc.info_type, 3)
        self.assertEqual(doc.certification_number, 2)
        self.assertEqual({line.code: line.measured_quantity for line in doc.iter_budget_lines() if line.kind == 'item'}, {'A': 2, 'B': 1})

    def test_manual_order_exports_a_structured_certificate(self):
        product = self.env['product.product'].create({'name': 'Pintura', 'type': 'service'})
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.env['sale.order.line'].create({'order_id': order.id, 'display_type': 'line_section', 'name': 'Acabados'})
        line = self.env['sale.order.line'].create({
            'order_id': order.id, 'product_id': product.id, 'product_uom_qty': 10,
            'price_unit': 20, 'tax_ids': [(6, 0, [])],
        })
        order.action_confirm()
        cert = self.env['construction.certification'].create({
            'sale_order_id': order.id, 'date': '2026-08-01', 'retention_percent': 0,
        })
        self.env['construction.certification.line'].create({
            'certification_id': cert.id, 'sale_line_id': line.id, 'qty_period': 4,
        })
        cert.action_measure()
        cert.action_approve()
        result = cert.action_export_bc3()
        attachment = self.env['ir.attachment'].browse(int(result['url'].split('/')[3].split('?')[0]))
        doc = parse_bc3(attachment.datas.content, strict=True)
        self.assertEqual(doc.info_type, 3)
        self.assertEqual([item.measured_quantity for item in doc.iter_budget_lines() if item.kind == 'item'], [4])
        self.assertTrue(any(item.kind == 'chapter' for item in doc.iter_budget_lines()))

    def test_invalid_reporting_period_is_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['construction.certification'].create({
                'sale_order_id': self.order.id, 'period_date_start': '2026-07-31',
                'period_date_end': '2026-07-01',
            })

    def test_origin_invoice_report_renders_standard_invoice(self):
        cert = self._cert('2026-06-01', self.sale_a, 2)
        cert.action_create_invoice()
        invoice = cert.invoice_id
        report = self.env.ref('tl_construction_certification.action_report_origin_invoice')
        html, _ = self.env['ir.actions.report']._render_qweb_html(report.id, invoice.ids)
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn('Partida uno', html)
        self.assertIn(cert.name, html)
        self.assertIn('o_total_table', html)
