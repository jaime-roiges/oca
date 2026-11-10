# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Odoo 20 packaging is a sale UoM (product.uom_ids), not product.packaging."""
import math

from babel.numbers import format_decimal


def _tl_format_quantity(quantity, language):
    return format_decimal(
        quantity, format="#,##0.######", locale=language or "en_US",
    )


def _tl_whole_package_quantity(quantity):
    """Accept only whole packaging counts; tolerate floating-point artefacts."""
    return (
        math.isfinite(quantity)
        and quantity > 0
        and math.isclose(quantity, round(quantity), rel_tol=0.0, abs_tol=1e-8)
    )


def _tl_packaging_summary(line, product, sale_uom, language):
    """Return balances in original contract UoM AND selected website sale UoM.

    Never round UP when deriving a purchase maximum; e.g. 1,000 units =
    83 complete boxes of 12 plus 4 units. Conversion uses Odoo 20 UoM factor.
    """
    source_uom = line.product_uom
    default_uom = product.uom_id
    remaining = max(0.0, line.remaining_uom_qty)
    sale_uom = sale_uom or default_uom
    equivalent = max(0.0, source_uom._compute_quantity(remaining, sale_uom, round=False))
    default_equivalent = max(
        0.0, source_uom._compute_quantity(remaining, default_uom, round=False)
    )
    is_packaging = sale_uom != default_uom
    complete = max(0, math.floor(equivalent + 1e-9)) if is_packaging else 0
    complete_in_default = (
        sale_uom._compute_quantity(complete, default_uom, round=False)
        if is_packaging else 0.0
    )
    leftover = max(0.0, default_equivalent - complete_in_default)
    # Round very small conversion noise to zero (not to a whole unit).
    if math.isclose(leftover, 0.0, abs_tol=1e-8):
        leftover = 0.0
    force_whole = bool(product.tl_contract_whole_pack_only and is_packaging)
    maximum = float(complete) if force_whole else equivalent
    return {
        "selected_uom_id": sale_uom.id,
        "selected_uom_name": sale_uom.name,
        "available_selected_qty": equivalent,
        "available_selected_display": _tl_format_quantity(equivalent, language),
        "maximum_orderable_qty": maximum,
        "full_packages": complete,
        "full_packages_display": _tl_format_quantity(complete, language),
        "leftover_base_qty": leftover,
        "leftover_base_display": _tl_format_quantity(leftover, language),
        "main_uom_name": default_uom.name,
        "package_size_in_base": (
            sale_uom._compute_quantity(1, default_uom, round=False)
            if is_packaging else 1.0
        ),
        "package_size_display": _tl_format_quantity(
            sale_uom._compute_quantity(1, default_uom, round=False)
            if is_packaging else 1.0, language,
        ),
        "is_packaging": is_packaging,
        "show_equivalent": sale_uom != source_uom,
        "whole_pack_only": force_whole,
    }
