#!/usr/bin/env python3
"""Standalone static checks for the tl_demo_sales_generator Odoo 20 addon.

Usage: python tools/check_odoo20_static.py
Does not require an Odoo server or any third-party dependencies.
"""
import ast
import csv
import io
import py_compile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
manifest = ast.literal_eval((ROOT / "__manifest__.py").read_text(encoding="utf-8"))
assert manifest["version"].startswith("20.0."), manifest["version"]
assert "security/ir.access.csv" in manifest["data"]
assert "security/ir.model.access.csv" not in manifest["data"]
for relative_path in manifest["data"]:
    assert (ROOT / relative_path).is_file(), relative_path
for source in ROOT.rglob("*.py"):
    py_compile.compile(str(source), cfile="/tmp/tl_demo_check.pyc", doraise=True)
for xml in ROOT.rglob("*.xml"):
    tree = ElementTree.parse(xml)
    for search in tree.getroot().iter("search"):
        assert list(search.iter("field")), f"No searchable fields in {xml}"
        for group in search.iter("group"):
            assert not ({"expand", "string"} & set(group.attrib)), (
                f"Odoo 20 forbids expand/string attributes on search-view groups: {xml}"
            )
        for filt in search.iter("filter"):
            assert filt.get("name"), f"Search filter lacks name in {xml}"
security = ROOT / "security/ir.access.csv"
with security.open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
assert rows and set(rows[0]) == {"id", "name", "model_id", "group_id/id", "operation", "domain"}
for row in rows:
    assert row["operation"] in {"cru", "crud"}
    assert row["model_id"].startswith("tl.demo.generation.")
print("OK: manifest, files, Python, XML and Odoo 20 search groups/security")
