# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from lib.bc3_parser import Bc3Error, parse_bc3
from lib.bc3_certification_export import export_certification, budget_from_order


class TestBc3CertificationExport(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'samples/presupuesto_demo.bc3').read_bytes()
        doc = parse_bc3(self.source, strict=True)
        self.lines = [line for line in doc.iter_budget_lines() if line.kind == 'item']
        self.quantities = {'.'.join(line.position): line.quantity / 2 for line in self.lines}

    def test_roundtrip_keeps_tree_prices_and_cumulative_quantities(self):
        payload = export_certification(self.source, self.quantities, 2, date(2026, 2, 28))
        document = parse_bc3(payload, strict=True)
        self.assertEqual(document.info_type, 3)
        self.assertEqual(document.certification_number, 2)
        self.assertEqual(document.certification_date, '2026-02-28')
        exported = [line for line in document.iter_budget_lines() if line.kind == 'item']
        self.assertEqual([x.code for x in exported], [x.code for x in self.lines])
        self.assertEqual([x.price for x in exported], [x.price for x in self.lines])
        for line in exported:
            self.assertAlmostEqual(line.measured_quantity, self.quantities['.'.join(line.position)])
        self.assertIn('Albañileria', payload.decode('utf-8'))

    def test_zero_is_explicit_and_roundtrips(self):
        zero = {key: 0 for key in self.quantities}
        out = export_certification(self.source, zero, 3, date(2026, 3, 31))
        measured = [line.measured_quantity for line in parse_bc3(out, strict=True).iter_budget_lines() if line.kind == 'item']
        self.assertEqual(measured, [0.0] * len(self.lines))

    def test_rejects_missing_position_and_over_budget(self):
        with self.assertRaises(Bc3Error):
            export_certification(self.source, {}, 2, date(2026, 2, 28))
        values = dict(self.quantities)
        first = self.lines[0]
        values['.'.join(first.position)] = first.quantity + 1
        with self.assertRaises(Bc3Error):
            export_certification(self.source, values, 2, date(2026, 2, 28))

    def test_rejects_unrepresentable_measurement(self):
        values = dict(self.quantities)
        values['.'.join(self.lines[0].position)] = 0.123456789
        with self.assertRaises(Bc3Error):
            export_certification(self.source, values, 2, date(2026, 2, 28))

    def test_rejects_type_three_as_original_budget(self):
        result = export_certification(self.source, self.quantities, 2, date(2026, 2, 28))
        with self.assertRaises(Bc3Error):
            export_certification(result, self.quantities, 3, date(2026, 3, 31))

    def test_manual_order_with_sections_roundtrips(self):
        rows = [
            {'id': 1, 'kind': 'line_section', 'name': 'Albañilería'},
            {'id': 2, 'kind': 'item', 'name': 'Tabique', 'unit': 'm²', 'quantity': 10.25, 'price': 23.45},
            {'id': 3, 'kind': 'line_subsection', 'name': 'Acabados'},
            {'id': 4, 'kind': 'item', 'name': 'Pintura', 'unit': 'm²', 'quantity': 20, 'price': 3},
        ]
        budget, positions = budget_from_order(rows, 'EUR')
        self.assertEqual(positions, {'1.1': 2, '1.2.1': 4})
        cert = export_certification(budget, {'1.1': 2.5, '1.2.1': 10}, 1, date(2026, 1, 31))
        document = parse_bc3(cert, strict=True)
        result = {'.'.join(line.position): line.measured_quantity for line in document.iter_budget_lines() if line.kind == 'item'}
        self.assertEqual(result, {'1.1': 2.5, '1.2.1': 10})

    def test_shared_chapter_with_different_measurements_is_rejected(self):
        source = '\n'.join([
            '~V|Test|FIEBDC-3/2024|Tests|Budget|UTF-8|x|2|',
            '~C|R##||Root||||', '~C|S#||Shared section||||', '~C|A|u|Work|10||0|',
            '~D|R##|S#\\1\\1\\S#\\1\\1\\|', '~D|S#|A\\1\\4\\|',
            '~M|S\\A|1\\1\\|4|||', '~M|S\\A|2\\1\\|4|||',
        ]).encode()
        with self.assertRaises(Bc3Error):
            export_certification(source, {'1.1': 1, '2.1': 2}, 1, date(2026, 1, 31))

    def test_inherited_chapter_and_item_factors_are_preserved(self):
        source = '\n'.join([
            '~V|Test|FIEBDC-3/2024|Tests|Budget|UTF-8|x|2|',
            '~C|R##||Root||||', '~C|S#||Section||||', '~C|A|u|Work|10||0|',
            '~D|R##|S#\\2\\1\\|', '~D|S#|A\\2\\5\\|',
            '~M|S\\A|1\\1\\|5|||',
        ]).encode()
        result = export_certification(source, {'1.1': 8}, 1, date(2026, 1, 31))
        doc = parse_bc3(result, strict=True)
        item = next(line for line in doc.iter_budget_lines() if line.kind == 'item')
        self.assertEqual(item.measured_quantity, 8)
