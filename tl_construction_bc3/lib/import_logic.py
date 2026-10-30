# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Pure, independently testable safety rules for BC3 economic imports."""

from .bc3_parser import Bc3Error


def certification_period(measured_origin, previously_committed_net, contract, tolerance=1e-6):
    """Translate a cumulative FIEBDC certificate into a nonnegative period.

    A smaller origin requires a credit note/revision, never a negative work
    certification. Posted credit notes are deducted from the committed origin.
    """
    if measured_origin < -tolerance:
        raise Bc3Error("La medición a origen no puede ser negativa.")
    if measured_origin > contract + tolerance:
        raise Bc3Error(
            "La medición a origen %s supera el contrato %s."
            % (measured_origin, contract)
        )
    if measured_origin + tolerance < previously_committed_net:
        raise Bc3Error(
            "El origen BC3 (%s) es inferior al origen neto previamente "
            "certificado (%s); tramite un abono antes de importar."
            % (measured_origin, previously_committed_net)
        )
    difference = measured_origin - previously_committed_net
    return 0.0 if abs(difference) <= tolerance else difference


def budget_key(position):
    """Uniquely identify a line occurrence, even with repeated concept codes."""
    return ".".join(position)


def validate_budget_keys(lines):
    keys = [budget_key(line.position) for line in lines]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise Bc3Error("Estructura de posiciones BC3 duplicada o incompleta.")
    return keys


def validated_budget_total(lines):
    """Compute an economic total without unchecked floating-point overflow.

    This preflight runs before products, orders and/or financial certifications
    are created. The parser separately validates inputs and decompositions.
    """
    from decimal import Decimal, InvalidOperation
    import math

    total = Decimal("0")
    for line in lines:
        if line.kind != "item":
            continue
        if not math.isfinite(line.quantity) or not math.isfinite(line.price):
            raise Bc3Error("Cantidad o precio BC3 no finito: %s." % line.code)
        try:
            amount = Decimal(str(line.quantity)) * Decimal(str(line.price))
        except (InvalidOperation, ValueError) as error:
            raise Bc3Error("Importe de partida BC3 inválido: %s." % line.code) from error
        if abs(amount) > Decimal("1e18"):
            raise Bc3Error("Importe de partida BC3 desbordado: %s." % line.code)
        total += amount
        if abs(total) > Decimal("1e18"):
            raise Bc3Error("Importe total BC3 desbordado: %s." % line.code)
    return float(total)


def coefficient_origin_ratio(executed_base, contracted_base, tolerance=1e-6):
    """Cumulative progress of measured BC3 work valued at CONTRACT prices.

    CI, GG, BI and the award discount are contractual SO lines, normally with
    quantity 1. They must move with the economic progress of the measured
    work, not with their own non-existent ~M or the source's current ~K rates.
    Contract and execution bases must use the same tax-excluded price policy.
    """
    import math

    if not all(math.isfinite(value) for value in (executed_base, contracted_base)):
        raise Bc3Error("Base económica BC3 no finita para coeficientes.")
    if contracted_base <= tolerance:
        raise Bc3Error("No se pueden distribuir coeficientes sin base de obra positiva.")
    if executed_base < -tolerance or executed_base > contracted_base + tolerance:
        raise Bc3Error(
            "Ejecución de obra %s fuera del importe contractual %s para coeficientes."
            % (executed_base, contracted_base)
        )
    ratio = executed_base / contracted_base
    return min(max(ratio, 0.0), 1.0)
