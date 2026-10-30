# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Standalone FIEBDC-3 parser tests. Run without Odoo:

    python -m unittest tests.test_bc3_parser
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.bc3_parser import (  # noqa: E402
    Bc3Error,
    coefficient_amounts,
    parse_bc3,
    parse_bc3_date,
    parse_number,
)

SAMPLE = """~V|Propiedad de prueba|FIEBDC-3/2024\\15062024|Grok Test|Presupuesto demo|ANSI|Obra ejemplo|2|||
~K|2\\2\\2\\3\\2\\2\\2\\2\\eur\\|6\\13\\6\\0\\21|
~C|OBRA##||Reforma local||||
~C|01#||Demoliciones||||
~C|01.01#||Demolicion interior||||
~C|DEM01|m2|Demolicion tabique|25.5|01012024|0|
~T|DEM01|Demolicion de tabique de ladrillo
incluyendo carga a contenedor.|
~C|02#||Albañileria||||
~C|TAB01|m2|Tabique ladrillo hueco|40|01012024|0|
~C|MO01|h|Oficial primera|20||1|
~C|MAT01|ud|Ladrillo hueco|0,3||3|
~C|%AUX|%|Medios auxiliares|||
~D|OBRA##|01#\\1\\1\\02#\\1\\1\\|
~D|01#|01.01#\\1\\1\\|
~D|01.01#|DEM01\\1\\12.5\\|
~D|02#|TAB01\\1\\30\\|
~D|TAB01|MO01\\1\\0.8\\MAT01\\1\\18\\%AUX\\1\\0.02\\|
~M|01.01#\\DEM01|1\\1\\1\\|12.5|\\ zona A \\ 10 \\ 1.25 \\ \\ \\ 1 \\ subtotal \\ \\ \\ \\ \\|2.1|
~M|02#\\TAB01||30|\\ zona \\ 30 \\ \\ \\ \\|
~Y|02#|PA01\\1\\1\\|
~C|PA01|pa|Partida alzada|500||0|
~N|02#\\TAB01|||\\ extra \\ 2 \\ 1.5 \\ \\ \\|
"""


class TestBc3Parser(unittest.TestCase):
    def test_numbers_and_dates(self):
        with self.assertRaises(Bc3Error):
            parse_number("importe-no-numerico")
        self.assertEqual(parse_number("102,8"), 102.8)
        self.assertEqual(parse_number("1.234,56"), 1234.56)
        self.assertEqual(parse_number("1,234.56"), 1234.56)
        self.assertEqual(parse_number("0"), 0.0)
        self.assertIsNone(parse_number("  "))
        self.assertEqual(parse_bc3_date("15062024"), "2024-06-15")
        self.assertEqual(parse_bc3_date("120699"), "1999-06-12")
        self.assertEqual(parse_bc3_date("401"), "2001-04-01")
        self.assertEqual(parse_bc3_date("061281"), "1981-12-06")

    def test_budget_tree_measurements_and_prices(self):
        document = parse_bc3(SAMPLE)
        self.assertEqual(document.info_type, 2)
        self.assertEqual(document.charset, "ANSI")
        self.assertEqual(document.version, "FIEBDC-3/2024")
        self.assertEqual(document.version_date, "2024-06-15")
        self.assertEqual(document.ci, 6)
        self.assertEqual(document.gg, 13)
        self.assertEqual(document.bi, 6)
        self.assertEqual(document.iva, 21)
        self.assertEqual(document.currency, "EUR")
        self.assertTrue(document.get("OBRA").is_root)
        self.assertFalse(document.get("OBRA").is_chapter)
        self.assertTrue(document.get("01").is_chapter)
        self.assertEqual(document.get("DEM01").text.splitlines()[0], "Demolicion de tabique de ladrillo")
        self.assertIn("contenedor", document.get("DEM01").text)
        self.assertEqual(document.get("MAT01").prices, [0.3])
        self.assertEqual(document.get("MAT01").concept_type, "3")

        tab = document.get("TAB01")
        self.assertAlmostEqual(document.composition_cost(tab), 21.83)
        self.assertEqual(document.unit_price(tab), 40)
        self.assertTrue(any("TAB01" in warning for warning in document.warnings))
        self.assertAlmostEqual(document.unit_price(tab, prefer_decomposition=True), 21.83)

        codes = [line.code for line in document.iter_budget_lines()]
        self.assertEqual(codes, ["01", "01.01", "DEM01", "02", "TAB01", "PA01"])
        dem = document.iter_budget_lines()[2]
        self.assertEqual(dem.kind, "item")
        self.assertEqual(dem.depth, 3)
        self.assertAlmostEqual(dem.quantity, 12.5)
        self.assertAlmostEqual(dem.price, 25.5)
        self.assertEqual(dem.label, "2.1")
        # ~N adds 2 * 1.5 to the previous total of 30.
        tab_line = document.iter_budget_lines()[4]
        self.assertAlmostEqual(tab_line.quantity, 33.0)
        self.assertEqual(document.iter_budget_lines()[5].code, "PA01")
        catalog = {concept.code for concept in document.catalog_concepts()}
        self.assertIn("MO01", catalog)
        self.assertIn("MAT01", catalog)
        self.assertNotIn("01", catalog)
        self.assertNotIn("%AUX", catalog)
        self.assertNotIn("OBRA", catalog)

    def test_expression_subtotal_and_coefficients(self):
        text = "\n".join(
            [
                "~V|Obra|FIEBDC-3/2024|Prog|Cab|850|Comentario|3|2|15032026|",
                "~C|R##||Raiz||||",
                "~C|P1|m|Zanja|10||0|",
                "~D|R##|P1\\1\\1\\|",
                "~M|R\\P1|1\\|18|3\\a*b+p\\2\\4\\\\\\1\\parcial\\\\\\\\\\2\\acumulado\\\\\\\\\\|Z-1|",
            ]
        )
        document = parse_bc3(text)
        self.assertEqual(document.info_type, 3)
        self.assertEqual(document.certification_number, 2)
        self.assertEqual(document.certification_date, "2026-03-15")
        line = document.iter_budget_lines()[0]
        # A certificate is always cumulative and cannot rewrite the contract.
        # The contract can legitimately be ONE unit.
        self.assertAlmostEqual(line.quantity, round(8 + 3.1415926, 2))
        self.assertAlmostEqual(line.measured_quantity, round(8 + 3.1415926, 2))
        self.assertEqual(line.label, "Z-1")
        certified = parse_bc3(
            "\n".join(
                [
                    "~V|Obra|FIEBDC-3/2024|Prog|Cab|850|c|3|1|01012026|",
                    "~C|R##||Raiz||||",
                    "~C|P1|m2|Solado|20||0|",
                    "~D|R##|P1\\1\\100\\|",
                    "~M|R\\P1||40|||",
                ]
            )
        ).iter_budget_lines()[0]
        self.assertAlmostEqual(certified.quantity, 40)
        self.assertAlmostEqual(certified.measured_quantity, 40)
        self.assertRaisesRegex(Bc3Error, "Incoherencia", lambda: parse_bc3(
            "\n".join([
                "~V|Obra|FIEBDC-3/2024|Prog|Cab|850|c|3|1|01012026|",
                "~C|R##||Raiz||||", "~C|P1|m2|Solado|20||0|",
                "~D|R##|P1\\1\\100\\|", "~M|R\\P1||40|||",
            ]), strict=True,
        ).iter_budget_lines())
        ci, baja, gg, bi = coefficient_amounts(1000, ci=0, gg=13, bi=6, baja=10)
        self.assertEqual(ci, 0)
        self.assertEqual(baja, 100)
        self.assertEqual(gg, 117)
        self.assertEqual(bi, 54)

    def test_charset_synonym_rename_and_empty_price_fallback(self):
        body = "~V|Base|FIEBDC-3/2020|Prog|Cab|850|Base|1|\n~C|CANON|u|Cañón|12,5||3|\n~C|ALIAS\\CANON|u||||\n"
        raw = body.encode("cp850") + b"\x1a"
        document = parse_bc3(raw)
        self.assertEqual(document.encoding, "cp850")
        self.assertEqual(document.get("CANON").summary, "Cañón")
        self.assertEqual(document.get("ALIAS").code, "CANON")
        renamed = parse_bc3("~C|A01|u|Viejo|0||3|\n~B|A01|A02|\n~D|R##|A02\\2\\|\n~C|R##||Raiz|||\n")
        self.assertIsNone(renamed.get("A01"))
        self.assertEqual(renamed.get("A02").summary, "Viejo")
        self.assertEqual(renamed.get("A02").prices, [0.0])
        child = renamed.get("R").children[0]
        self.assertEqual(child.factor, 2)
        self.assertEqual(child.yield_qty, 1)
        self.assertEqual(parse_bc3("~V|X|FIEBDC-3/2024|P|C|ANSI|c|1|\n~C|M1|kg|Cemento|||\n").get("M1").unit, "kg")

    def test_utf8_and_decomposition_percentage_mask(self):
        text = "~V|X|FIEBDC-3/2024|P|C||c|1|\n~C|P|u|Partida|0||0|\n~C|OP1|u|Op|10||3|\n~C|XX1|u|Otro|10||3|\n~C|OP%N|%|Porcentaje|||\n~D|P|OP1\\1\\2\\XX1\\1\\1\\OP%N\\1\\0.5\\|\n"
        raw = text.encode("utf-8")
        document = parse_bc3(raw)
        # 50% only on codes starting with OP: 2*10 = 20, plus XX 10, plus 10.
        self.assertAlmostEqual(document.composition_cost(document.get("P")), 40.0)
        self.assertEqual(document.unit_price(document.get("P")), 40.0)

    def test_rejects_empty_file(self):
        with self.assertRaises(Bc3Error):
            parse_bc3(b"\x1a")
        with self.assertRaises(Bc3Error):
            parse_bc3("~V|Solo version|FIEBDC-3/2024|")

    def test_explicit_percentage_allocation_is_not_full_mask(self):
        bc3 = "\n".join([
            "~C|R##||Root||||", "~C|P|u|Work|0|||",
            "~C|X|u|X|10|||", "~C|Y|u|Y|20|||",
            "~C|%A|%|Aux||", "~D|R##|P\\1\\1\\|",
            "~D|P||X\\1\\1\\%A\\Y\\1\\1\\\\%A\\1\\0.1\\|",
        ])
        document = parse_bc3(bc3)
        self.assertAlmostEqual(document.composition_cost(document.get("P")), 31.0)

    def test_repeated_code_measurement_is_selected_by_tree_position(self):
        bc3 = "\n".join([
            "~C|R##||Root||||", "~C|ITEM|u|Repeated|1|||",
            "~D|R##|ITEM\\1\\1\\ITEM\\1\\1\\|",
            "~M|R\\ITEM|2\\|20||Second|",
            "~M|R\\ITEM|1\\|10||First|",
        ])
        lines = parse_bc3(bc3).iter_budget_lines()
        self.assertEqual([line.quantity for line in lines], [10, 20])
        self.assertEqual([line.position for line in lines], [("1",), ("2",)])
        self.assertEqual([line.label for line in lines], ["First", "Second"])
        ambiguous = bc3.replace("2\\|20", "\\|20").replace("1\\|10", "\\|10")
        with self.assertRaisesRegex(Bc3Error, "ambigua"):
            parse_bc3(ambiguous).iter_budget_lines()

    def test_rename_updates_existing_composition_and_measurements(self):
        bc3 = "\n".join([
            "~C|R##||Root||||", "~C|OLD|u|Original|25|||",
            "~D|R##|OLD\\1\\10\\|",
            "~M|R\\OLD|1\\|8||Label|",
            "~B|OLD|NEW|",
        ])
        document = parse_bc3(bc3)
        self.assertIsNone(document.get("OLD"))
        line = document.iter_budget_lines()[0]
        self.assertEqual((line.code, line.quantity, line.price), ("NEW", 8, 25))
        self.assertEqual(line.label, "Label")
        self.assertEqual(document.root_concept().children[0].code, "NEW")

    def test_rejects_cyclic_tree_and_decomposition(self):
        bc3 = "\n".join([
            "~C|R##||Root||||", "~C|C#||Chapter||||",
            "~D|R##|C#\\1\\1\\|", "~D|C#|R##\\1\\1\\|",
        ])
        with self.assertRaisesRegex(Bc3Error, "Ciclo"):
            parse_bc3(bc3).iter_budget_lines()
        price_cycle = "\n".join([
            "~C|P|u|P|0|||", "~C|Q|u|Q|0|||",
            "~D|P|Q\\1\\1\\|", "~D|Q|P\\1\\1\\|",
        ])
        doc = parse_bc3(price_cycle)
        with self.assertRaisesRegex(Bc3Error, "circular"):
            doc.composition_cost(doc.get("P"))

    def test_nonfinite_values_and_invalid_dates_are_not_accepted(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e1000"):
            with self.subTest(value=value), self.assertRaises(Bc3Error):
                parse_number(value)
        self.assertIsNone(parse_bc3_date("31022026"))
        self.assertIsNone(parse_bc3_date("990199"))
        self.assertEqual(parse_bc3_date("29022024"), "2024-02-29")
        with self.assertRaisesRegex(Bc3Error, "Fecha"):
            parse_bc3("~V|X|FIEBDC-3/2024|P|C|850|c|3|1|31022026|\n~C|P|u|P|1|||")

    def test_measurement_details_are_kept_for_auditing(self):
        bc3 = "\n".join([
            "~C|R##||Root||||", "~C|A|m2|Facade|10|||",
            "~D|R##|A\\1\\10\\|",
            "~M|R\\A|1\\|10|\\wall#IFC-11\\2\\5\\1\\\\|Fachada|",
        ])
        lines = parse_bc3(bc3).iter_budget_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].measurement_lines[0].bim_ids, ["IFC-11"])
        self.assertEqual(lines[0].measurement_lines[0].units, 2)
        self.assertEqual(lines[0].measured_quantity, 10)


if __name__ == "__main__":
    unittest.main()
