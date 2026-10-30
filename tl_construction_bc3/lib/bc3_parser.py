# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Parser for FIEBDC-3/2024 (.BC3) files.

The parser depends only on the standard library so it can be tested without
an Odoo database. It reads the records needed to rebuild a price catalogue
and a budget:

* ``~V`` property, version, charset, information type and certification
* ``~K`` indirect costs, overheads, industrial profit, baja and VAT
* ``~C`` concepts (root ``##``, chapters ``#``, synonyms)
* ``~D`` / ``~Y`` decomposition (factor defaults to 1, yield defaults to 1)
* ``~T`` long description
* ``~M`` / ``~N`` measurements, including subtotals and type-3 expressions
* ``~B`` code rename / deletion

Waste (``~R``, ``~X``), parametric families (``~P``) and specifications
(``~L``) are recognised and counted, not imported.
"""

from __future__ import annotations

import re
import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import Counter
from datetime import date
from dataclasses import dataclass, field

_WS_BEFORE_SEP = re.compile(r"[ \t\r\n]+(?=[|\\~])")
_PI = 3.1415926

INFO_DATABASE = 1
INFO_BUDGET = 2
INFO_CERTIFICATION = 3
INFO_UPDATE = 4
_MAX_NESTED_LEVELS = 128
# Source numbers and calculated amounts must remain within a sensible, finite
# economic range before reaching an ORM Float/Monetary field.
_MAX_ECONOMIC_VALUE = 1e18
_DEFAULT_DECIMALS = {
    "DRC": 3, "DC": 2, "DFS": 3, "DRS": 3, "DUO": 2,
    "DI": 2, "DES": 2, "DN": 2, "DD": 2, "DS": 2,
    "DSP": 2, "DEC": 2,
}
_K_EXTENDED_NAMES = tuple(_DEFAULT_DECIMALS)
_K_LEGACY_NAMES = ("DN", "DD", "DS", "DR", "DI", "DP", "DC", "DM")

_ENCODINGS = {
    "850": "cp850",
    "437": "cp437",
    "ANSI": "cp1252",
    "UTF-8": "utf-8",
    "UTF8": "utf-8",
}


class Bc3Error(ValueError):
    """The file is not a readable FIEBDC-3 document."""


@dataclass
class Bc3Child:
    code: str
    factor: float = 1.0
    yield_qty: float = 1.0
    percentage_codes: list[str] = field(default_factory=list)

    @property
    def is_percentage(self) -> bool:
        return is_percentage_code(self.code)


@dataclass
class Bc3MeasurementLine:
    tipo: str = ""
    comment: str = ""
    bim_ids: list[str] = field(default_factory=list)
    units: float | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    value: float = 0.0


@dataclass
class Bc3Measurement:
    parent: str
    child: str
    position: tuple[str, ...] = ()
    stated_total: float | None = None
    label: str = ""
    lines: list[Bc3MeasurementLine] = field(default_factory=list)
    total: float = 0.0
    appended_measurements: bool = False

    def recompute(self, warnings: list[str] | None = None) -> float:
        self.total = measurement_total(self.lines, self.stated_total, warnings)
        return self.total


@dataclass
class Bc3Concept:
    code: str
    synonyms: list[str] = field(default_factory=list)
    is_root: bool = False
    is_chapter: bool = False
    unit: str = ""
    summary: str = ""
    prices: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    concept_type: str = ""
    text: str = ""
    children: list[Bc3Child] = field(default_factory=list)


@dataclass
class Bc3BudgetLine:
    kind: str
    depth: int
    code: str
    name: str
    unit: str
    quantity: float
    measured_quantity: float | None
    price: float
    factor: float
    yield_qty: float
    label: str
    concept_type: str
    text: str
    position: tuple[str, ...] = ()
    measurement_lines: list[Bc3MeasurementLine] = field(default_factory=list)


@dataclass
class Bc3Document:
    encoding: str = "cp850"
    charset: str = "850"
    property: str = ""
    version: str = ""
    version_date: str | None = None
    program: str = ""
    header: str = ""
    labels: list[str] = field(default_factory=list)
    comment: str = ""
    info_type: int | None = None
    certification_number: int | None = None
    certification_date: str | None = None
    url_base: str = ""
    ci: float = 0.0
    gg: float = 0.0
    bi: float = 0.0
    baja: float = 0.0
    iva: float = 0.0
    currency: str = ""
    concepts: dict[str, Bc3Concept] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    measurements: dict[tuple[str, str], list[Bc3Measurement]] = field(
        default_factory=dict
    )
    warnings: list[str] = field(default_factory=list)
    ignored: dict[str, int] = field(default_factory=dict)
    strict: bool = False
    price_scope: int = 1
    decimals: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_DECIMALS))
    price_scopes: list[str] = field(default_factory=list)

    def precision(self, name: str) -> int:
        return abs(self.decimals.get(name, _DEFAULT_DECIMALS.get(name, 2)))

    def round_value(self, value: float, name: str, context: str) -> float:
        return _round_bc3(value, self.precision(name), context)

    def concept_price(self, concept: Bc3Concept) -> float:
        if not concept.prices:
            return 0.0
        if self.price_scope > len(concept.prices):
            self.warnings.append(
                "El concepto %s no tiene precio para ámbito %s; "
                "se usa el último valor disponible." % (concept.code, self.price_scope)
            )
        price = concept.prices[min(self.price_scope - 1, len(concept.prices) - 1)]
        return self.round_value(
            price, "DUO" if concept.children else "DES",
            "precio del concepto %s" % concept.code,
        )

    def _raise_or_warn(self, message: str) -> None:
        if self.strict:
            raise Bc3Error(message)
        self.warnings.append(message)

    def validate_measurements(self) -> None:
        """Check detailed arithmetic and declared totals, retaining raw audit lines."""
        for key, bucket in self.measurements.items():
            for measurement in bucket:
                for line in measurement.lines:
                    if line.units is not None:
                        line.units = self.round_value(line.units, "DN", "unidades ~M %s" % (key,))
                    for attr in ("length", "width", "height"):
                        value = getattr(line, attr)
                        if value is not None:
                            setattr(line, attr, self.round_value(value, "DD", "dimensión ~M %s" % (key,)))
                if measurement.stated_total is not None:
                    measurement.stated_total = self.round_value(
                        measurement.stated_total, "DS", "MEDICION_TOTAL de %s" % (key,)
                    )
                detailed = bool(measurement.lines) and any(
                    line.tipo == "3" or _has_dimensions(line) for line in measurement.lines
                    if line.tipo not in ("1", "2")
                )
                total = measurement.recompute(self.warnings)
                measurement.total = self.round_value(total, "DS", "total calculado ~M %s" % (key,))
                if detailed and measurement.stated_total is not None and not measurement.appended_measurements:
                    tolerance = max(1e-9, 10 ** (-self.precision("DS")) / 2)
                    if abs(measurement.total - measurement.stated_total) > tolerance:
                        self._raise_or_warn(
                            "Medición ~M %s posición %s: total declarado %s "
                            "distinto de las líneas detalladas %s."
                            % (key, ".".join(measurement.position) or "-",
                               _fmt(measurement.stated_total), _fmt(measurement.total))
                        )

    def get(self, code: str | None) -> Bc3Concept | None:
        if not code:
            return None
        key = canonical_code(code)
        if not key:
            return None
        concept = self.concepts.get(key)
        if concept is not None:
            return concept
        primary = self.aliases.get(key)
        if primary:
            return self.concepts.get(primary)
        return None

    def root_concept(self) -> Bc3Concept | None:
        roots = [concept for concept in self.concepts.values() if concept.is_root]
        if roots:
            return roots[0]
        child_codes = set()
        for concept in self.concepts.values():
            for child in concept.children:
                child_codes.add(canonical_code(child.code))
        parents = [
            concept
            for concept in self.concepts.values()
            if concept.children and concept.code not in child_codes
        ]
        if len(parents) == 1:
            return parents[0]
        return None

    def catalog_concepts(self) -> list[Bc3Concept]:
        result = []
        for concept in self.concepts.values():
            if concept.is_root or concept.is_chapter:
                continue
            if is_percentage_code(concept.code):
                continue
            if (concept.unit or "").strip() == "%":
                continue
            if concept.concept_type == "5":
                continue
            result.append(concept)
        return result

    def unit_price(self, concept: Bc3Concept, prefer_decomposition: bool = False) -> float:
        """Contract price of a concept.

        The ``~C`` price is the budget price. A decomposition is used when
        that price is missing, or when ``prefer_decomposition`` is set and a
        direct cost can be calculated. Differences above two cents are
        reported either way: FIEBDC gives precedence to ``~D``, but an
        incomplete justification must not replace the contract price unless
        the caller asks for it.
        """
        stated = self.concept_price(concept)
        computed = self.composition_cost(concept)
        if computed is None:
            return stated
        if stated and abs(computed - stated) > 0.02:
            self.warnings.append(
                "Precio de %s: el concepto indica %s y la descomposición %s."
                % (concept.code, _fmt(stated), _fmt(computed))
            )
        if prefer_decomposition or not stated:
            return computed
        return stated

    def composition_cost(
        self, concept: Bc3Concept, stack: set[str] | None = None
    ) -> float | None:
        """Evaluate the decomposition; reject cyclic dependencies explicitly.

        Explicit percentage allocations take precedence over code masks, as
        prescribed by FIEBDC-3/2024 for CODIGO_PORCENTAJE.
        """
        if not concept.children:
            return None
        stack = set() if stack is None else stack
        if len(stack) >= _MAX_NESTED_LEVELS:
            raise Bc3Error("La descomposición BC3 supera 128 niveles anidados.")
        if concept.code in stack:
            raise Bc3Error(
                "Descomposición circular BC3: %s -> %s"
                % (" -> ".join(sorted(stack)), concept.code)
            )
        stack.add(concept.code)
        rows: list[tuple[str, float, list[str]]] = []
        has_component = False
        try:
            for child in concept.children:
                if child.is_percentage:
                    explicit = any(child.code in allocations for _, _, allocations in rows)
                    prefix = percentage_prefix(child.code)
                    base = sum(
                        amount for code, amount, allocations in rows
                        if (child.code in allocations if explicit else (
                            not prefix or code.startswith(prefix)
                        ))
                    )
                    amount = _safe_product(
                        base, child.factor, child.yield_qty,
                        context="porcentaje %s" % child.code,
                    )
                    rows.append((child.code, self.round_value(amount, "DI", "porcentaje %s" % child.code), []))
                    continue
                target = self.get(child.code)
                if target is None or target.is_chapter or target.is_root:
                    continue
                has_component = True
                nested = self.composition_cost(target, stack)
                price = nested if nested is not None else self.concept_price(target)
                amount = _safe_product(
                    child.factor, child.yield_qty, price,
                    context="componente %s de %s" % (child.code, concept.code),
                )
                rows.append((
                    child.code, self.round_value(amount, "DI", "importe de %s" % child.code),
                    child.percentage_codes,
                ))
        finally:
            stack.discard(concept.code)
        if not has_component:
            return None
        total = _safe_sum((amount for _, amount, _ in rows), "descomposición de %s" % concept.code)
        return self.round_value(total, "DUO", "precio descompuesto de %s" % concept.code)

    def iter_budget_lines(self, prefer_decomposition: bool = False) -> list[Bc3BudgetLine]:
        """Build lines with stable tree positions (not merely concept codes)."""
        root = self.root_concept()
        if root is None:
            self.warnings.append(
                "El archivo no tiene concepto raíz ni un único capítulo de partida."
            )
            return []

        occurrences = Counter()

        def count_children(parent, ancestry):
            if len(ancestry) >= _MAX_NESTED_LEVELS:
                raise Bc3Error("La jerarquía BC3 supera 128 niveles anidados.")
            if parent.code in ancestry:
                raise Bc3Error(
                    "Ciclo en árbol BC3: %s -> %s" % (
                        " -> ".join(ancestry), parent.code
                    )
                )
            for child in parent.children:
                if child.is_percentage:
                    continue
                key = (canonical_code(parent.code), canonical_code(child.code))
                occurrences[key] += 1
                target = self.get(child.code)
                if target and (target.is_root or target.is_chapter):
                    count_children(target, ancestry + (parent.code,))

        count_children(root, ())
        buckets = {key: list(value) for key, value in self.measurements.items()}

        def take_measurement(parent, child, position):
            key = (canonical_code(parent), canonical_code(child))
            bucket = buckets.get(key, [])
            if not bucket:
                return None
            exact = next((m for m in bucket if m.position == position), None)
            if exact is not None:
                bucket.remove(exact)
                return exact
            # Unpositioned measurements are only unambiguous if the occurrence
            # is unique in the whole tree. Never assign them by arbitrary order.
            if occurrences[key] != 1:
                if any(not m.position for m in bucket):
                    raise Bc3Error(
                        "Medición ambigua para %s/%s: POSICION obligatoria en partidas repetidas."
                        % key
                    )
                return None
            unpositioned = [measurement for measurement in bucket if not measurement.position]
            if len(unpositioned) == 1 and len(bucket) == 1:
                measurement = unpositioned[0]
                bucket.remove(measurement)
                return measurement
            if any(measurement.position for measurement in bucket):
                self._raise_or_warn(
                    "POSICION explícita de medición %s/%s no coincide con la "
                    "posición del árbol %s: %s. No se reasigna automáticamente."
                    % (parent, child, ".".join(position), ", ".join(
                        ".".join(measurement.position) for measurement in bucket
                        if measurement.position
                    ))
                )
            return None

        lines: list[Bc3BudgetLine] = []

        def add_child(parent, child, depth, position, ancestry, inherited_factor=1.0):
            if child.is_percentage:
                return
            target = self.get(child.code)
            measurement = take_measurement(parent.code, child.code, position)
            label = measurement.label if measurement else ""
            if target is None:
                raise Bc3Error(
                    "La partida %s aparece en ~D pero carece de definición ~C."
                    % child.code
                )
            if target.is_chapter or target.is_root:
                if target.code in ancestry:
                    raise Bc3Error(
                        "Ciclo de capítulos BC3: %s -> %s"
                        % (" -> ".join(ancestry), target.code)
                    )
                line = _budget_line(
                    "chapter", depth, target, 0.0, None, 0.0,
                    child.factor, child.yield_qty, label,
                )
                line.position = position
                lines.append(line)
                # A repeated chapter scales every work item in its subtree.
                # ~M still records the LOCAL child's yield, so inherited
                # factors are applied only after validating the local ~D/~M.
                next_factor = _safe_product(
                    inherited_factor, child.factor, child.yield_qty,
                    context="factor heredado de capítulo %s" % target.code,
                )
                for index, grandchild in enumerate(target.children, 1):
                    add_child(
                        target, grandchild, depth + 1,
                        position + (str(index),), ancestry + (target.code,),
                        next_factor,
                    )
                return
            if self.info_type in (INFO_BUDGET, INFO_CERTIFICATION):
                if measurement is None:
                    self._raise_or_warn(
                        "Partida %s posición %s sin registro ~M: "
                        "medición no verificable."
                        % (child.code, ".".join(position))
                    )
                else:
                    d_quantity = self.round_value(child.yield_qty, "DS", "rendimiento de %s" % child.code)
                    m_quantity = self.round_value(measurement.total, "DS", "medición de %s" % child.code)
                    if abs(d_quantity - m_quantity) > 10 ** (-self.precision("DS")) / 2:
                        self._raise_or_warn(
                            "Incoherencia ~D/~M de %s posición %s: "
                            "rendimiento %s, medición %s."
                            % (child.code, ".".join(position), _fmt(d_quantity), _fmt(m_quantity))
                        )
            total_factor = _safe_product(
                inherited_factor, child.factor,
                context="factor efectivo de %s" % child.code,
            )
            budget_qty = _safe_product(total_factor, child.yield_qty, context="cantidad de %s" % child.code)
            quantity, measured = _quantities(self, budget_qty, measurement, total_factor)
            line = _budget_line(
                "item", depth, target, quantity, measured,
                self.unit_price(target, prefer_decomposition),
                child.factor, child.yield_qty, label,
            )
            line.position = position
            line.measurement_lines = list(measurement.lines) if measurement else []
            lines.append(line)

        depth = 1
        if not root.is_root and (root.is_chapter or root.children):
            root_line = _budget_line(
                "chapter", 1, root, 0.0, None, 0.0, 1.0, 1.0, ""
            )
            root_line.position = ("0",)
            lines.append(root_line)
            depth = 2
        for index, child in enumerate(root.children, 1):
            add_child(root, child, depth, (str(index),), (root.code,))
        return lines


def _budget_line(
    kind, depth, concept, quantity, measured_quantity, price, factor, yield_qty, label
):
    return Bc3BudgetLine(
        kind=kind,
        depth=depth,
        code=concept.code,
        name=concept.summary or concept.code,
        unit=concept.unit or "",
        quantity=quantity,
        measured_quantity=measured_quantity,
        price=price,
        factor=factor,
        yield_qty=yield_qty,
        label=label,
        concept_type=concept.concept_type or "",
        text=concept.text or "",
    )


def _quantities(document: Bc3Document, budget_qty: float, measurement, factor: float):
    """Return the effective budget quantity and measured origin.

    ``~M.MEDICION_TOTAL`` reproduces the *yield* of the corresponding ``~D``
    child, NOT the full contracted/certified quantity.  Both the measured and
    unmeasured routes must multiply that yield by ``~D.FACTOR``.  Keeping the
    raw measurement separately on the BC3 line preserves its audit detail.
    A type-3 document describes cumulative execution, never the SO contract.
    """
    if measurement is None:
        return document.round_value(budget_qty, "DS", "cantidad efectiva ~D"), None
    effective = _safe_product(
        factor, measurement.total, context="cantidad efectiva ~D/~M"
    )
    effective = document.round_value(effective, "DS", "cantidad medida efectiva")
    return effective, effective


def parse_bc3(source: bytes | str, *, strict: bool = False, price_scope: int = 1) -> Bc3Document:
    """Parse a FIEBDC-3/2024 document from bytes or text."""
    if isinstance(source, str):
        text = source
        encoding = "utf-8"
        charset = "UTF-8"
    else:
        if not source or not source.strip(b"\x00 \t\r\n\x1a"):
            raise Bc3Error("El archivo BC3 está vacío.")
        text, encoding, charset = decode_bc3(source)
    if not isinstance(price_scope, int) or price_scope <= 0 or price_scope > 50:
        raise Bc3Error("Ámbito de precios BC3 fuera de rango (1..50).")
    document = Bc3Document(
        encoding=encoding, charset=charset or "850",
        strict=strict, price_scope=price_scope,
    )
    for kind, fields in iter_records(text):
        handler = _HANDLERS.get(kind)
        if handler is None:
            document.ignored[kind] = document.ignored.get(kind, 0) + 1
            continue
        handler(document, fields)
    if not document.concepts:
        raise Bc3Error("El archivo BC3 no contiene conceptos (~C).")
    document.validate_measurements()
    # Validate any values that could be transmitted directly to the ERP.
    for concept in document.concepts.values():
        # FIEBDC ~K also specifies the decimals of the operand factor and
        # rendement, not only the final amount. Normalize operands before
        # evaluating any budget quantity or decomposed price.
        factor_precision = "DRC" if concept.is_root or concept.is_chapter else "DFS"
        yield_precision = "DRC" if concept.is_root or concept.is_chapter else "DRS"
        for component in concept.children:
            for attr, precision in (("factor", factor_precision),
                                    ("yield_qty", yield_precision)):
                original = getattr(component, attr)
                rounded = document.round_value(
                    original, precision,
                    "~D de %s / %s (%s)" % (concept.code, component.code, attr),
                )
                if original != rounded:
                    document.warnings.append(
                        "~D %s/%s: %s %s redondeado a %s según ~K."
                        % (concept.code, component.code, attr, original, rounded)
                    )
                setattr(component, attr, rounded)
        for index, raw_price in enumerate(concept.prices, 1):
            precision = "DUO" if concept.children else "DES"
            rounded = document.round_value(raw_price, precision, "precio ~C %s" % concept.code)
            if rounded != raw_price:
                document.warnings.append(
                    "Precio ~C %s ámbito %s redondeado de %s a %s según ~K (%s)."
                    % (concept.code, index, raw_price, rounded, precision)
                )
            concept.prices[index - 1] = rounded
    return document


def decode_bc3(raw: bytes) -> tuple[str, str, str]:
    payload = raw
    if payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
        return payload.decode("utf-8"), "utf-8", "UTF-8"
    payload = payload.replace(b"\x1a", b"")
    latin = payload.decode("latin-1")
    charset = _charset_of(latin)
    encoding = _ENCODINGS.get((charset or "").upper(), "cp850")
    if not charset:
        # Spec default is code page 850. Accept UTF-8 when it is unambiguous
        # and the file actually contains non-ASCII text.
        if _looks_like_utf8(payload):
            encoding = "utf-8"
            charset = "UTF-8"
        else:
            charset = "850"
    try:
        return payload.decode(encoding), encoding, charset
    except UnicodeDecodeError as error:
        raise Bc3Error("Codificación BC3 inválida para %s" % charset) from error


def iter_records(text: str):
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _WS_BEFORE_SEP.sub("", normalized)
    for chunk in normalized.split("~"):
        if not chunk.strip():
            continue
        fields = chunk.split("|")
        kind = fields[0].strip().upper()[:1]
        if not kind or not kind.isalpha():
            continue
        yield kind, fields


def canonical_code(code: str) -> str:
    base, _root, _chapter = classify_code(code or "")
    return base


def classify_code(raw: str) -> tuple[str, bool, bool]:
    code = (raw or "").strip()
    if code.endswith("##"):
        return code[:-2].rstrip("#"), True, False
    if code.endswith("#"):
        return code[:-1].rstrip("#"), False, True
    return code, False, False


def is_percentage_code(code: str) -> bool:
    return "%" in (code or "") or "&" in (code or "")


def percentage_prefix(code: str) -> str:
    for index, char in enumerate(code or ""):
        if char in "%&":
            return code[:index]
    return ""


def parse_number(value: str | None) -> float | None:
    text = (value or "").strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        result = float(text)
    except (ValueError, OverflowError) as error:
        raise Bc3Error("Número BC3 inválido: %s" % value) from error
    if not math.isfinite(result) or abs(result) > _MAX_ECONOMIC_VALUE:
        raise Bc3Error("Número BC3 no finito o fuera de rango económico: %s" % value)
    return result


def parse_bc3_date(value: str | None) -> str | None:
    """Parse a FIEBDC date (DDMMAAAA, with the 80/20 rule) as ISO."""
    text = (value or "").strip()
    if not text or not text.isdigit():
        return None
    if len(text) % 2:
        text = "0" + text
    if len(text) <= 2:
        try:
            return date(_expand_year(text), 1, 1).isoformat()
        except ValueError:
            return None
    if len(text) <= 4:
        month = int(text[:-2] or "0")
        year = _expand_year(text[-2:])
        try:
            return date(year, month or 1, 1).isoformat()
        except ValueError:
            return None
    if len(text) == 6:
        day, month, year = int(text[:2]), int(text[2:4]), _expand_year(text[4:])
    else:
        day, month, year = int(text[:2]), int(text[2:4]), int(text[4:8])
    if month == 0:
        month = 1
    if day == 0:
        day = 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def coefficient_amounts(pem, ci=0.0, gg=0.0, bi=0.0, baja=0.0):
    """Amounts of CI, baja, overheads and industrial profit.

    Indirect costs are added to the material budget. The award discount
    (baja, or alza when negative) is applied on that base. Overheads and
    industrial profit are percentages of the result. VAT is not included.
    """
    ci_amount = _safe_product(pem or 0.0, (ci or 0.0) / 100.0, context="CI")
    base = _safe_sum((pem or 0.0, ci_amount), "base con costes indirectos")
    baja_amount = _safe_product(base, (baja or 0.0) / 100.0, context="baja")
    after = _safe_sum((base, -baja_amount), "base después de baja")
    gg_amount = _safe_product(after, (gg or 0.0) / 100.0, context="GG")
    bi_amount = _safe_product(after, (bi or 0.0) / 100.0, context="BI")
    return ci_amount, baja_amount, gg_amount, bi_amount


def measurement_total(lines, stated, warnings=None) -> float:
    if not lines:
        return stated if stated is not None else 0.0
    expression = None
    total = 0.0
    measurable = False
    meaningful = False
    for line in lines:
        if line.tipo == "3" and line.comment:
            expression = line.comment
        if line.tipo in ("1", "2"):
            continue
        measurable = True
        value = _line_value(line, expression, warnings)
        if not math.isfinite(value):
            raise Bc3Error("La medición BC3 produce un valor no finito.")
        line.value = value
        total = _safe_sum((total, value), "medición acumulada")
        if line.tipo == "3" or _has_dimensions(line):
            meaningful = True
    if not measurable:
        return stated if stated is not None else 0.0
    if not meaningful and stated not in (None, 0):
        return stated
    return total


def _ensure_economic(value: float, context: str) -> float:
    try:
        result = float(value)
    except (ValueError, OverflowError, TypeError) as error:
        raise Bc3Error("Valor económico inválido (%s)." % context) from error
    if not math.isfinite(result) or abs(result) > _MAX_ECONOMIC_VALUE:
        raise Bc3Error("Importe no finito o desbordado (%s)." % context)
    return result


def _round_bc3(value: float, decimals: int, context: str) -> float:
    _ensure_economic(value, context)
    if not 0 <= decimals <= 12:
        raise Bc3Error("Precisión ~K fuera de rango (%s): %s." % (context, decimals))
    try:
        quantum = Decimal(1).scaleb(-decimals)
        result = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
        return _ensure_economic(float(result), context)
    except (InvalidOperation, OverflowError) as error:
        raise Bc3Error("No se puede redondear el importe (%s)." % context) from error


def _safe_product(*values, context: str) -> float:
    result = Decimal("1")
    for value in values:
        _ensure_economic(value, context)
        result *= Decimal(str(value))
    return _ensure_economic(float(result), context)


def _safe_sum(values, context: str) -> float:
    result = Decimal("0")
    for value in values:
        _ensure_economic(value, context)
        result += Decimal(str(value))
    return _ensure_economic(float(result), context)


def eval_expression(expression: str, variables: dict[str, float]) -> float:
    """Evaluate a measurement expression (``a b c d``, ``p``, ``+ - * / ^``)."""
    parser = _ExprParser(expression, variables)
    return parser.parse()


def _line_value(line, expression, warnings) -> float:
    variables = {
        "a": line.units or 0.0,
        "b": line.length or 0.0,
        "c": line.width or 0.0,
        "d": line.height or 0.0,
        "p": _PI,
    }
    if expression:
        try:
            return eval_expression(expression, variables)
        except Bc3Error as error:
            if warnings is not None:
                warnings.append("Expresión de medición no evaluada (%s)." % error)
    dims = [
        value
        for value in (line.units, line.length, line.width, line.height)
        if value is not None
    ]
    if not dims:
        return 0.0
    value = 1.0
    for dim in dims:
        value = _safe_product(value, dim, context="línea de medición")
    return value


def _has_dimensions(line) -> bool:
    return any(
        value is not None
        for value in (line.units, line.length, line.width, line.height)
    )


def _expand_year(text: str) -> int:
    year = int(text)
    if len(text) <= 2:
        return 1900 + year if year >= 80 else 2000 + year
    return year


def _fmt(value: float) -> str:
    return ("%.4f" % value).rstrip("0").rstrip(".")


def _charset_of(latin_text: str) -> str:
    for kind, fields in iter_records(latin_text):
        if kind != "V":
            continue
        return _field(fields, 5).strip()
    return ""


def _looks_like_utf8(payload: bytes) -> bool:
    if not any(byte > 127 for byte in payload):
        return False
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _field(fields: list[str], index: int) -> str:
    if index >= len(fields):
        return ""
    return fields[index].strip()


def _subfields(value: str) -> list[str]:
    parts = value.split("\\")
    if parts and parts[-1] == "":
        parts.pop()
    return [part.strip() for part in parts]


def _numbers(parts: list[str]) -> list[float]:
    values = []
    for part in parts:
        number = parse_number(part)
        if number is not None:
            values.append(number)
    return values


def _handle_v(document: Bc3Document, fields: list[str]) -> None:
    document.property = _field(fields, 1)
    version_parts = _subfields(_field(fields, 2))
    if version_parts:
        document.version = version_parts[0]
    if len(version_parts) > 1:
        document.version_date = parse_bc3_date(version_parts[1])
        if version_parts[1] and document.version_date is None:
            raise Bc3Error("Fecha inválida en la versión ~V: %s" % version_parts[1])
    document.program = _field(fields, 3)
    header_parts = _subfields(_field(fields, 4))
    if header_parts:
        document.header = header_parts[0]
        document.labels = header_parts[1:]
    charset = _field(fields, 5)
    if charset:
        document.charset = charset
    document.comment = _field(fields, 6)
    info = parse_number(_field(fields, 7))
    if info is not None and (info != int(info) or int(info) not in (1, 2, 3, 4)):
        raise Bc3Error("Tipo de información ~V inválido: %s." % info)
    document.info_type = int(info) if info is not None else None
    number = parse_number(_field(fields, 8))
    if number is not None and (number != int(number) or number < 0):
        raise Bc3Error("Número de certificación ~V inválido: %s." % number)
    document.certification_number = int(number) if number is not None else None
    document.certification_date = parse_bc3_date(_field(fields, 9))
    if _field(fields, 9) and document.certification_date is None:
        raise Bc3Error("Fecha de certificación BC3 inválida: %s" % _field(fields, 9))
    document.url_base = _field(fields, 10)


def _handle_k(document: Bc3Document, fields: list[str]) -> None:
    coeffs = _subfields(_field(fields, 2))
    values = [parse_number(part) or 0.0 for part in coeffs[:5]]
    while len(values) < 5:
        values.append(0.0)
    document.ci, document.gg, document.bi, document.baja, document.iva = values
    extended = _subfields(_field(fields, 3))
    if extended:
        if len(extended) % 13:
            document._raise_or_warn(
                "Registro ~K: bloque de precisiones extendidas incompleto "
                "(se esperan 13 subcampos por ámbito)."
            )
        else:
            groups = [extended[index:index + 13]
                      for index in range(0, len(extended), 13)]
            document.price_scopes = [group[-1].upper() for group in groups]
            if document.price_scope > len(groups):
                raise Bc3Error(
                    "El ámbito de precios %s no existe en ~K (%s disponibles)."
                    % (document.price_scope, len(groups))
                )
            group = groups[document.price_scope - 1]
            for key, raw in zip(_K_EXTENDED_NAMES, group[:12]):
                document.decimals[key] = _parse_precision(raw, key)
            document.currency = group[12].upper() or document.currency
    elif _field(fields, 1):
        legacy = _subfields(_field(fields, 1))
        for key, raw in zip(_K_LEGACY_NAMES, legacy[:8]):
            precision = _parse_precision(raw, key)
            if key in _DEFAULT_DECIMALS:
                document.decimals[key] = precision
            elif key == "DR":
                for name in ("DRC", "DFS", "DRS"):
                    document.decimals[name] = precision
            elif key == "DP":
                document.decimals["DUO"] = precision
            elif key == "DM":
                document.decimals["DSP"] = precision
        if len(legacy) > 8 and legacy[8].strip():
            document.currency = legacy[8].upper()
    document.currency = document.currency or _currency_of(fields)


def _parse_precision(raw: str, key: str) -> int:
    if not raw:
        return _DEFAULT_DECIMALS.get(key, 2)
    try:
        value = int(raw)
    except ValueError as error:
        raise Bc3Error("Precisión ~K no numérica para %s: %s." % (key, raw)) from error
    if abs(value) > 12:
        raise Bc3Error("Precisión ~K fuera de rango para %s: %s." % (key, raw))
    return value


def _currency_of(fields: list[str]) -> str:
    extended = _subfields(_field(fields, 3))
    if extended:
        for part in reversed(extended):
            if part.isalpha():
                return part.upper()
    legacy = _subfields(_field(fields, 1))
    if len(legacy) >= 9 and legacy[8].isalpha():
        return legacy[8].upper()
    return ""


def _handle_c(document: Bc3Document, fields: list[str]) -> None:
    codes = [code for code in _subfields(_field(fields, 1)) if code]
    if not codes:
        return
    concept = None
    for raw in codes:
        existing = document.get(raw)
        if existing is not None:
            concept = existing
            break
    primary, is_root, is_chapter = classify_code(codes[0])
    if not primary:
        return
    if concept is None:
        concept = Bc3Concept(code=primary)
        document.concepts[primary] = concept
    elif concept.code != primary and primary not in document.aliases:
        document.aliases[primary] = concept.code
    concept.is_root = concept.is_root or is_root
    concept.is_chapter = concept.is_chapter or is_chapter
    for raw in codes[1:]:
        alias, alias_root, alias_chapter = classify_code(raw)
        if not alias or alias == concept.code:
            continue
        document.aliases[alias] = concept.code
        if alias not in concept.synonyms:
            concept.synonyms.append(alias)
        concept.is_root = concept.is_root or alias_root
        concept.is_chapter = concept.is_chapter or alias_chapter
    unit = _field(fields, 2)
    summary = _field(fields, 3)
    if unit:
        concept.unit = unit
    if summary and summary.upper() != "NUL":
        concept.summary = summary
    elif summary.upper() == "NUL":
        concept.summary = ""
    price_field = _field(fields, 4)
    if price_field:
        concept.prices = _numbers(_subfields(price_field))
    date_field = _field(fields, 5)
    if date_field:
        dates = []
        for raw_date in _subfields(date_field):
            parsed = parse_bc3_date(raw_date)
            if raw_date and parsed is None:
                document._raise_or_warn(
                    "Fecha de concepto ~C inválida (%s): %s." % (concept.code, raw_date)
                )
            if parsed:
                dates.append(parsed)
        concept.dates = dates
    concept_type = _field(fields, 6)
    if concept_type:
        concept.concept_type = concept_type


def _handle_text(document: Bc3Document, fields: list[str]) -> None:
    concept = document._ensure(fields)
    text = _field(fields, 2)
    if not concept or not text:
        return
    if text.upper() == "NUL":
        concept.text = ""
    else:
        concept.text = text


def _handle_d(document: Bc3Document, fields: list[str]) -> None:
    _set_children(document, fields, replace=True)


def _handle_y(document: Bc3Document, fields: list[str]) -> None:
    _set_children(document, fields, replace=False)


def _set_children(document: Bc3Document, fields: list[str], replace: bool) -> None:
    parent = document._ensure(fields)
    if parent is None:
        return
    children = _parse_children(fields)
    if replace:
        parent.children = children
    else:
        parent.children.extend(children)


def _parse_children(fields: list[str]) -> list[Bc3Child]:
    extended = _field(fields, 3)
    legacy = _field(fields, 2)
    if extended:
        groups = _aligned_groups(_subfields(extended), 4, pad=False)
        if groups is None:
            groups = _aligned_groups(_subfields(extended), 3, pad=True)
        if groups:
            children = [child for child in (_child_from_group(group) for group in groups) if child]
            if children:
                return children
    groups = _aligned_groups(_subfields(legacy), 3, pad=True) or []
    return [child for child in (_child_from_group(group) for group in groups) if child]


def _aligned_groups(parts: list[str], size: int, pad: bool) -> list[list[str]] | None:
    if not parts:
        return []
    if size == 4 and len(parts) % 4 == 3:
        parts = parts + [""]
    remainder = len(parts) % size
    if remainder:
        if not pad:
            return None
        parts = parts + [""] * (size - remainder)
    return [parts[index : index + size] for index in range(0, len(parts), size)]


def _child_groups(parts: list[str], size: int) -> list[list[str]] | None:
    return _aligned_groups(parts, size, pad=False)


def _child_from_group(group: list[str]) -> Bc3Child | None:
    code = group[0].strip() if group else ""
    if not code:
        return None
    factor = parse_number(group[1]) if len(group) > 1 else None
    yield_qty = parse_number(group[2]) if len(group) > 2 else None
    percentages = []
    if len(group) > 3 and group[3]:
        percentages = [part.strip() for part in group[3].split(";") if part.strip()]
    return Bc3Child(
        code=canonical_code(code) or code.strip(),
        factor=1.0 if factor is None else factor,
        yield_qty=1.0 if yield_qty is None else yield_qty,
        percentage_codes=percentages,
    )


def _handle_m(document: Bc3Document, fields: list[str]) -> None:
    _set_measurement(document, fields, replace=True)


def _handle_n(document: Bc3Document, fields: list[str]) -> None:
    _set_measurement(document, fields, replace=False)


def _set_measurement(document: Bc3Document, fields: list[str], replace: bool) -> None:
    parent, child = _measurement_identity(_field(fields, 1))
    if not child:
        return
    position = tuple(part for part in _subfields(_field(fields, 2)) if part)
    stated = parse_number(_field(fields, 3))
    lines = _measurement_lines(_field(fields, 4))
    label = _field(fields, 5)
    key = (parent, child)
    bucket = document.measurements.setdefault(key, [])
    existing = None
    if position:
        for measurement in bucket:
            if measurement.position == position:
                existing = measurement
                break
    elif len(bucket) == 1:
        existing = bucket[0]
    if existing is None:
        existing = Bc3Measurement(parent=parent, child=child, position=position)
        bucket.append(existing)
        replace = True
    if replace:
        existing.lines = lines
        existing.appended_measurements = False
    else:
        existing.lines.extend(lines)
        existing.appended_measurements = stated is None
        if stated is None:
            # ~N adds measurements after the original ~M stated_total; the
            # original declared total must not be compared to the new sum.
            existing.stated_total = None
    if stated is not None:
        existing.stated_total = stated
    if label:
        existing.label = label
    if position:
        existing.position = position
    existing.recompute(document.warnings)


def _measurement_identity(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in value.split("\\") if part.strip()]
    if len(parts) >= 2:
        return canonical_code(parts[0]), canonical_code(parts[1])
    if parts:
        return "", canonical_code(parts[0])
    return "", ""


def _measurement_lines(value: str) -> list[Bc3MeasurementLine]:
    parts = _subfields(value)
    if not parts:
        return []
    groups = _child_groups(parts, 6)
    if groups is None:
        raise Bc3Error("Línea de medición ~M/~N incompleta: faltan subcampos.")
    lines = []
    for group in groups:
        comment, bim_ids = _split_bim(group[1] if len(group) > 1 else "")
        lines.append(
            Bc3MeasurementLine(
                tipo=(group[0] if group else "").strip(),
                comment=comment,
                bim_ids=bim_ids,
                units=parse_number(group[2]) if len(group) > 2 else None,
                length=parse_number(group[3]) if len(group) > 3 else None,
                width=parse_number(group[4]) if len(group) > 4 else None,
                height=parse_number(group[5]) if len(group) > 5 else None,
            )
        )
    return lines


def _split_bim(raw: str) -> tuple[str, list[str]]:
    if "#" not in raw:
        return raw.strip(), []
    parts = raw.split("#")
    comment = parts[0].strip()
    bim_ids = [part.strip() for part in parts[1:] if part.strip()]
    return comment, bim_ids


def _handle_b(document: Bc3Document, fields: list[str]) -> None:
    old = canonical_code(_field(fields, 1))
    new = canonical_code(_field(fields, 2))
    concept = document.get(old)
    if concept is None:
        raise Bc3Error("~B hace referencia al código desconocido %s" % old)
    primary = concept.code
    if new and new != primary and document.get(new):
        raise Bc3Error("~B: el código destino %s ya existe" % new)
    if new == primary:
        return

    # Maintain all references from ~D / ~Y and ~M / ~N; aliases alone would
    # leave a stale, non-resolvable child when the former key is deleted.
    for parent in document.concepts.values():
        if not new:
            parent.children = [
                child for child in parent.children
                if canonical_code(child.code) != primary
            ]
        else:
            for child in parent.children:
                if canonical_code(child.code) == primary:
                    child.code = new
                child.percentage_codes = [
                    new if canonical_code(code) == primary else code
                    for code in child.percentage_codes
                ]
    rewritten = {}
    for (parent, child), measurements in document.measurements.items():
        if not new and primary in (parent, child):
            continue
        parent = new if parent == primary else parent
        child = new if child == primary else child
        for measurement in measurements:
            measurement.parent = parent
            measurement.child = child
        rewritten.setdefault((parent, child), []).extend(measurements)
    document.measurements = rewritten
    document.concepts.pop(primary, None)
    document.aliases = {
        alias: (new if target == primary else target)
        for alias, target in document.aliases.items()
        if new and alias != primary and alias != new
        and target != alias
    }
    if new:
        concept.code = new
        document.concepts[new] = concept


def _ensure(self: Bc3Document, fields: list[str]) -> Bc3Concept | None:
    raw = _field(fields, 1)
    if not raw:
        return None
    concept = self.get(raw)
    if concept is not None:
        _base, is_root, is_chapter = classify_code(raw)
        concept.is_root = concept.is_root or is_root
        concept.is_chapter = concept.is_chapter or is_chapter
        return concept
    base, is_root, is_chapter = classify_code(raw)
    if not base:
        return None
    concept = Bc3Concept(code=base, is_root=is_root, is_chapter=is_chapter)
    self.concepts[base] = concept
    return concept


Bc3Document._ensure = _ensure  # type: ignore[attr-defined]


class _ExprParser:
    def __init__(self, expression: str, variables: dict[str, float]):
        self.text = (expression or "").replace(" ", "").replace(",", ".")
        self.variables = variables
        self.index = 0

    def parse(self) -> float:
        if not self.text:
            raise Bc3Error("expresión vacía")
        value = self._expression()
        if self.index != len(self.text):
            raise Bc3Error(self.text)
        return value

    def _expression(self) -> float:
        value = self._term()
        while self._at("+-"):
            operator = self._pop()
            right = self._term()
            value = _safe_sum((value, right if operator == "+" else -right), "expresión suma")
        return _ensure_economic(value, "expresión de medición")

    def _term(self) -> float:
        value = self._power()
        while self._at("*/"):
            operator = self._pop()
            right = self._power()
            if operator == "/" and right == 0:
                raise Bc3Error("división por cero")
            value = _safe_product(value, right, context="expresión producto") if operator == "*" else _ensure_economic(value / right, "expresión división")
        return value

    def _power(self) -> float:
        value = self._unary()
        if self._at("^"):
            self._pop()
            power = self._power()
            try:
                value = _ensure_economic(value ** power, "expresión potencia")
            except (OverflowError, ZeroDivisionError, ValueError) as error:
                raise Bc3Error("Potencia no válida en medición.") from error
        return value

    def _unary(self) -> float:
        if self._at("+-"):
            operator = self._pop()
            value = self._unary()
            return value if operator == "+" else -value
        return self._primary()

    def _primary(self) -> float:
        char = self._peek()
        if char == "(":
            self._pop()
            value = self._expression()
            if self._pop() != ")":
                raise Bc3Error("paréntesis")
            return value
        if char.isalpha():
            self._pop()
            if char not in self.variables:
                raise Bc3Error("variable %s" % char)
            return float(self.variables[char])
        if char.isdigit() or char == ".":
            start = self.index
            self._pop()
            while self._peek().isdigit() or self._peek() == ".":
                self._pop()
            return _ensure_economic(float(self.text[start : self.index]), "literal expresión")
        raise Bc3Error(self.text[self.index :] or "fin")

    def _peek(self) -> str:
        if self.index >= len(self.text):
            return ""
        return self.text[self.index]

    def _at(self, chars: str) -> bool:
        char = self._peek()
        return bool(char) and char in chars

    def _pop(self) -> str:
        char = self._peek()
        if char:
            self.index += 1
        return char


_HANDLERS = {
    "V": _handle_v,
    "K": _handle_k,
    "C": _handle_c,
    "D": _handle_d,
    "Y": _handle_y,
    "T": _handle_text,
    "M": _handle_m,
    "N": _handle_n,
    "B": _handle_b,
}
