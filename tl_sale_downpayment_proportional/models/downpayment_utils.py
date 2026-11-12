# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Calculation helpers independent of Odoo's ORM (easy to regression-test)."""

from copy import deepcopy


def allocation_amount(
    currency,
    full_base,
    available,
    current_product_base,
    order_product_base,
    invoice_room,
    is_last,
):
    """Return the untaxed amount available for one original advance line."""
    if is_last:
        requested = available
    else:
        requested = currency.round(
            full_base * current_product_base / order_product_base
        )
    return currency.round(min(max(0.0, requested), available, invoice_room))


def scaled_extra_tax_data(extra_tax_data, factor):
    """Scale manually assigned base/tax values without changing quantity.

    With native Odoo 20 advances, quantity is always 1 or -1, whereas the
    manual tax values in extra_tax_data encode the down payment's real base.
    """
    result = deepcopy(extra_tax_data or {})
    if "price_unit" in result:
        result["price_unit"] *= factor
    for key in ("manual_total_excluded_currency", "manual_total_excluded"):
        if key in result:
            result[key] *= factor
    for amounts in result.get("manual_tax_amounts", {}).values():
        for key in (
            "base_amount",
            "base_amount_currency",
            "tax_amount",
            "tax_amount_currency",
        ):
            if key in amounts:
                amounts[key] *= factor
    return result
