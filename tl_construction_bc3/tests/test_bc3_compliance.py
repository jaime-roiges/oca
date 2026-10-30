# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Regressions from the second critical audit of 20.0.1.2.0."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.bc3_parser import Bc3Error, parse_bc3  # noqa: E402


def certificate(d_qty=70, m_qty=70, detail="", certificate_number=2):
    return "\n".join([
        "~V|Construction|FIEBDC-3/2024|Tests|Facade|UTF-8|c|3|%s|30092026|" % certificate_number,
        "~C|R##||Root||||", "~C|A|m2|Work|20.00|01012026|0|",
        "~D|R##|A\\1\\%s\\|" % d_qty,
        "~M|R\\A|1\\|%s|%s|Facade|" % (m_qty, detail),
    ])


class TestBc3Compliance(unittest.TestCase):
    def test_type_three_measures_origin_not_contract(self):
        doc = parse_bc3(certificate(), strict=True)
        [line] = doc.iter_budget_lines()
        self.assertEqual(line.quantity, 70)
        self.assertEqual(line.measured_quantity, 70)
        # 100 m2 remains on the Odoo contract, not in this type-3 document.

    def test_d_factor_multiplies_measured_effective_quantity(self):
        source = "\n".join([
            "~V|Construction|FIEBDC-3/2024|Tests|Facade|UTF-8|c|2|",
            "~C|R##||Root||||", "~C|A|m2|Work|10||0|",
            "~D|R##|A\\2\\5\\|",
            "~M|R\\A|1\\|5|||",
        ])
        [line] = parse_bc3(source, strict=True).iter_budget_lines()
        self.assertEqual(line.factor, 2)
        self.assertEqual(line.yield_qty, 5)
        self.assertEqual(line.measured_quantity, 10)
        self.assertEqual(line.quantity, 10)
        self.assertEqual(line.price * line.quantity, 100)

    def test_factor_in_cumulative_certificate(self):
        source = certificate(d_qty=35, m_qty=35).replace(
            "A\\1\\35", "A\\2\\35"
        )
        [line] = parse_bc3(source, strict=True).iter_budget_lines()
        self.assertEqual(line.quantity, 70)
        self.assertEqual(line.measured_quantity, 70)

    def test_chapter_factor_scales_nested_measured_work(self):
        source = "\n".join([
            "~V|Construction|FIEBDC-3/2024|Tests|Facade|UTF-8|c|2|",
            "~C|ROOT##||Root||||", "~C|CH#||Chapter|0||0|",
            "~C|A|m2|Work|10||0|",
            "~D|ROOT##|CH#\\2\\1\\|",
            "~D|CH#|A\\1\\5\\|",
            "~M|CH\\A|1\\1\\|5|||",
        ])
        document = parse_bc3(source, strict=True)
        work = [line for line in document.iter_budget_lines() if line.kind == "item"]
        self.assertEqual(len(work), 1)
        self.assertEqual(work[0].quantity, 10)
        self.assertEqual(work[0].measured_quantity, 10)

    def test_strict_rejects_different_d_and_m(self):
        with self.assertRaisesRegex(Bc3Error, "Incoherencia ~D/~M"):
            parse_bc3(certificate(d_qty=100, m_qty=70), strict=True).iter_budget_lines()
        doc = parse_bc3(certificate(d_qty=100, m_qty=70), strict=False)
        self.assertEqual(doc.iter_budget_lines()[0].quantity, 70)
        self.assertTrue(any("Incoherencia ~D/~M" in w for w in doc.warnings))

    def test_detail_differs_from_declared_m(self):
        detail = "\\Facade\\2\\5\\1\\\\"
        with self.assertRaisesRegex(Bc3Error, "total declarado"):
            parse_bc3(certificate(d_qty=10, m_qty=100, detail=detail), strict=True)
        doc = parse_bc3(certificate(d_qty=10, m_qty=100, detail=detail), strict=False)
        self.assertTrue(any("total declarado" in w for w in doc.warnings))
        self.assertEqual(doc.iter_budget_lines()[0].measured_quantity, 10)

    def test_incorrect_position_not_assigned_to_unique_item(self):
        source = certificate().replace("~M|R\\A|1\\|", "~M|R\\A|999\\|")
        with self.assertRaisesRegex(Bc3Error, "POSICION"):
            parse_bc3(source, strict=True).iter_budget_lines()
        doc = parse_bc3(source, strict=False)
        [line] = doc.iter_budget_lines()
        self.assertIsNone(line.measured_quantity)
        self.assertTrue(any("POSICION" in w for w in doc.warnings))

    def test_nonfinite_cost_cannot_escape_to_odoo(self):
        source = "\n".join([
            "~C|P|u|Work|0||0|",
            "~C|S|u|Material|100000000000000000||3|",
            "~D|P|S\\1\\100000000000000000\\|",
        ])
        doc = parse_bc3(source)
        with self.assertRaisesRegex(Bc3Error, "desbordado"):
            doc.composition_cost(doc.get("P"))

    def test_precision_and_half_up_rounding_from_extended_k(self):
        fmt = "\\".join(["3", "2", "3", "3", "2", "2", "2", "2", "2", "2", "2", "2", "EUR"])
        source = "~K||0\\0\\0\\0\\0|%s\\|\n~C|S|u|Simple|1.005|01012026|3|" % fmt
        doc = parse_bc3(source, strict=True)
        self.assertEqual(doc.precision("DES"), 2)
        self.assertAlmostEqual(doc.unit_price(doc.get("S")), 1.01)
        self.assertTrue(any("redondeado" in w for w in doc.warnings))

    def test_two_tariffs_are_scoped_independently(self):
        group_a = "\\".join(["3", "2", "3", "3", "2", "2", "2", "2", "2", "2", "2", "2", "EUR"])
        group_b = group_a[:-3] + "USD"
        source = "~K||0\\0\\0\\0\\0|%s\\%s\\|\n~C|S|u|Simple|10\\20\\|01012026|3|" % (group_a, group_b)
        doc1 = parse_bc3(source, price_scope=1)
        doc2 = parse_bc3(source, price_scope=2)
        self.assertEqual(doc1.unit_price(doc1.get("S")), 10)
        self.assertEqual(doc2.unit_price(doc2.get("S")), 20)
        self.assertEqual(doc2.currency, "USD")
        with self.assertRaisesRegex(Bc3Error, "no existe"):
            parse_bc3(source, price_scope=3)

    def test_invalid_concept_date_has_visible_diagnostic(self):
        source = "~C|A|u|Bad day|10|31022026|3|"
        with self.assertRaisesRegex(Bc3Error, "Fecha de concepto"):
            parse_bc3(source, strict=True)
        doc = parse_bc3(source)
        self.assertTrue(any("Fecha de concepto" in warning for warning in doc.warnings))

    def test_incomplete_file_is_only_allowed_in_compatibility_mode(self):
        source = "\n".join([
            "~V|X|FIEBDC-3/2024|P|C|850|c|2|",
            "~C|R##||Root||||", "~C|A|u|Work|10||0|",
            "~D|R##|A\\1\\2\\|",
        ])
        with self.assertRaisesRegex(Bc3Error, "sin registro ~M"):
            parse_bc3(source, strict=True).iter_budget_lines()
        doc = parse_bc3(source, strict=False)
        self.assertEqual(doc.iter_budget_lines()[0].quantity, 2)
        self.assertTrue(any("sin registro ~M" in w for w in doc.warnings))

    def test_wrong_precision_K_is_rejected(self):
        fmt = "\\".join(["3", "2", "999", "3", "2", "2", "2", "2", "2", "2", "2", "2", "EUR"])
        with self.assertRaisesRegex(Bc3Error, "Precisión ~K"):
            parse_bc3("~K||0\\0\\0\\0\\0|%s\\|\n~C|A|u|A|10||3|" % fmt)

    def test_measurement_add_record_not_a_spurious_mismatch(self):
        source = "\n".join([
            "~C|R##||Root||||", "~C|A|u|A|10||0|",
            "~D|R##|A\\1\\7\\|",
            "~M|R\\A|1\\|5|\\one\\1\\5\\1\\\\|",
            "~N|R\\A|1\\||\\extra\\1\\2\\1\\\\|",
        ])
        doc = parse_bc3(source, strict=False)
        self.assertEqual(doc.iter_budget_lines()[0].measured_quantity, 7)
        self.assertFalse(any("total declarado" in w for w in doc.warnings))


if __name__ == "__main__":
    unittest.main()
