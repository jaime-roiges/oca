# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""FIEBDC type-3 export based on an archived source budget.

The original concept definitions and ancillary records remain in the file.
Only measurements for budget work items are replaced by cumulative totals;
measurement breakdowns from the original budget are not presented as actual
certification measurements. Ambiguous shared decompositions are rejected.
"""
from datetime import date
import math

from .bc3_parser import Bc3Error, canonical_code, decode_bc3, iter_records, parse_bc3


def _number(value):
    if not math.isfinite(value):
        raise Bc3Error("La cantidad de certificación no es finita.")
    return format(value, '.12f').rstrip('0').rstrip('.') or '0'


def export_certification(source, cumulative_by_position, number, certification_date, price_scope=1):
    if not isinstance(number, int) or number <= 0:
        raise Bc3Error("La certificación debe tener un número positivo.")
    if not isinstance(certification_date, date):
        raise Bc3Error("La certificación debe tener una fecha válida.")
    text, _encoding, _charset = decode_bc3(source)
    doc = parse_bc3(source, strict=True, price_scope=price_scope)
    if doc.info_type != 2:
        raise Bc3Error("La exportación requiere el BC3 original de presupuesto (tipo 2).")
    lines = [line for line in doc.iter_budget_lines() if line.kind == 'item']
    expected = {'.'.join(line.position) for line in lines}
    if set(cumulative_by_position) != expected:
        raise Bc3Error("Las posiciones del presupuesto y de las mediciones no coinciden.")
    for line in lines:
        value = float(cumulative_by_position['.'.join(line.position)])
        if not math.isfinite(value) or value < 0 or value > line.quantity + 1e-7:
            raise Bc3Error("La medición acumulada está fuera del presupuesto en %s." % '.'.join(line.position))
    roots = doc.root_concept()
    if not roots:
        raise Bc3Error("No se ha identificado la raíz del presupuesto.")
    changed_parents = {}
    visited_child = {}
    measured = []
    item_pairs = set()
    item_codes = set()

    def traverse(parent, position=(), inherited=1.0, ancestry=()):
        if parent.code in ancestry:
            raise Bc3Error("El presupuesto tiene una jerarquía circular.")
        for index, child in enumerate(parent.children, 1):
            if child.is_percentage:
                continue
            target = doc.get(child.code)
            if not target:
                raise Bc3Error("Falta el concepto BC3 %s." % child.code)
            path = position + (str(index),)
            if target.is_root or target.is_chapter:
                traverse(target, path, inherited * child.factor * child.yield_qty, ancestry + (parent.code,))
                continue
            qty = float(cumulative_by_position['.'.join(path)])
            factor = inherited * child.factor
            if not math.isfinite(qty) or qty < 0 or not math.isfinite(factor) or factor <= 0:
                raise Bc3Error("Cantidad o factor no representable en %s." % '.'.join(path))
            local = qty / factor
            rounded = doc.round_value(local, 'DRC', 'rendimiento exportado')
            if abs(rounded * factor - qty) > 1e-7:
                raise Bc3Error("La precisión BC3 no representa la medición en %s." % '.'.join(path))
            key = id(child)
            if key in visited_child and abs(visited_child[key] - rounded) > 1e-9:
                raise Bc3Error("La misma descomposición reutilizada tiene mediciones incompatibles.")
            visited_child[key] = rounded
            child.yield_qty = rounded
            changed_parents[parent.code] = parent
            measured.append((parent.code, target.code, path, rounded))
            item_pairs.add((parent.code, target.code))
            item_codes.add(target.code)

    traverse(roots)
    records = []
    seen_header = False
    for kind, fields in iter_records(text):
        if kind == 'V':
            if seen_header:
                raise Bc3Error("El BC3 contiene más de un registro de versión.")
            seen_header = True
            fields = (fields + [''] * 11)[:max(11, len(fields))]
            fields[5] = 'UTF-8'
            fields[7] = '3'
            fields[8] = str(number)
            fields[9] = certification_date.strftime('%d%m%Y')
        elif kind in ('M', 'N') and len(fields) > 1:
            parts = [canonical_code(part) for part in fields[1].split('\\') if part.strip()]
            if len(parts) >= 2 and (parts[0], parts[1]) in item_pairs:
                continue
            if len(parts) == 1 and parts[0] in item_codes:
                continue
        records.append('~' + '|'.join(fields).rstrip('|') + '|')
    if not seen_header:
        raise Bc3Error("El BC3 no contiene un registro ~V.")
    for parent in changed_parents.values():
        components = []
        for child in parent.children:
            components.extend((child.code, _number(child.factor), _number(child.yield_qty), ';'.join(child.percentage_codes)))
        records.append('~D|%s||%s|'% (parent.code, '\\'.join(components) + '\\'))
    for parent, child, path, local in measured:
        records.append('~M|%s\\%s|%s\\|%s|||' % (parent, child, '\\'.join(path), _number(local)))
    output = ('\r\n'.join(records) + '\r\n').encode('utf-8')
    check = parse_bc3(output, strict=True, price_scope=price_scope)
    actual = {'.'.join(line.position): line.measured_quantity for line in check.iter_budget_lines() if line.kind == 'item'}
    if set(actual) != expected or any(actual[p] is None or abs(actual[p] - float(cumulative_by_position[p])) > 1e-7 for p in expected):
        raise Bc3Error("La verificación de las mediciones exportadas no coincide.")
    return output


def budget_from_order(records, currency):
    """Construct a BC3 budget from an order without an imported BC3.

    This preserves the order's sections and lines. It does not claim to add
    a price decomposition or measurement detail that does not exist in Odoo.
    """
    if not records or not currency or not currency.isascii() or not currency.isalpha():
        raise Bc3Error("Faltan partidas o moneda válidas para generar el presupuesto BC3.")
    def clean(value):
        return str(value or '').replace('~', '-').replace('|', '-').replace('\\', '-').replace('\r', ' ').replace('\n', ' ')

    root = 'TLROOT'
    parent = root
    current_section = root
    concepts = ['~C|%s##||Presupuesto de obra||||' % root]
    children = {root: []}
    mapping = {}
    names = set()
    for row in records:
        identifier = int(row['id'])
        if identifier <= 0 or identifier in names:
            raise Bc3Error("Las líneas del pedido no tienen identificadores únicos.")
        names.add(identifier)
        kind = row['kind']
        if kind in ('line_section', 'line_subsection'):
            code = 'S%s' % identifier
            parent = current_section if kind == 'line_subsection' and current_section != root else root
            children.setdefault(parent, []).append((code, 1.0))
            children[code] = []
            concepts.append('~C|%s#||%s||||' % (code, clean(row['name'])))
            if kind == 'line_section':
                current_section = code
            parent = code
            continue
        if kind != 'item':
            continue
        qty, price = float(row['quantity']), float(row['price'])
        if not math.isfinite(qty) or not math.isfinite(price) or qty < 0:
            raise Bc3Error("Una partida del pedido tiene cantidad o precio no válido.")
        code = 'L%s' % identifier
        children.setdefault(parent, []).append((code, qty))
        description = clean(row['name'])
        concepts.append('~C|%s|%s|%s|%s||0|' % (code, clean(row['unit']), description[:64], _number(price)))
        concepts.append('~T|%s|%s|' % (code, description))
        mapping[code] = identifier
    if not mapping:
        raise Bc3Error("El pedido no contiene partidas exportables.")
    records_out = ['~V|Tecniloop|FIEBDC-3/2024|Odoo|Presupuesto|UTF-8||2|',
                   '~K||0\\0\\0\\0\\0\\|6\\2\\6\\6\\6\\6\\6\\6\\6\\6\\6\\6\\%s\\|' % currency.upper()]
    records_out += concepts
    for code, childlist in children.items():
        if childlist:
            body = ''.join('%s\\1\\%s\\' % (child, _number(qty)) for child, qty in childlist)
            records_out.append('~D|%s|%s|' % (code, body))
    # The budget measurement records establish the stable tree positions.
    provisional = ('\r\n'.join(records_out) + '\r\n').encode('utf-8')
    doc = parse_bc3(provisional, strict=False)
    lines = [line for line in doc.iter_budget_lines() if line.kind == 'item']
    for line in lines:
        # Parent is found by walking the root along this stable position.
        node = doc.root_concept()
        for idx in line.position[:-1]:
            node = doc.get(node.children[int(idx) - 1].code)
        local = line.quantity
        records_out.append('~M|%s\\%s|%s\\|%s|||' % (node.code, line.code, '\\'.join(line.position), _number(local)))
    result = ('\r\n'.join(records_out) + '\r\n').encode('utf-8')
    verified = parse_bc3(result, strict=True)
    positions = {'.'.join(line.position): mapping[line.code] for line in verified.iter_budget_lines() if line.kind == 'item'}
    if len(positions) != len(mapping):
        raise Bc3Error("No se ha podido verificar toda la estructura del pedido.")
    return result, positions
