==============================
Purchase Order Triple Discount
==============================

Odoo 20 migration of OCA ``purchase_triple_discount`` 19.0.

This module provides three successive discounts on purchase order lines and vendor
pricelists. The effective discount is multiplicative. For example 10%, 20% and 30%
produce an effective discount of 49.6%.

It depends on ``account_invoice_triple_discount`` so the three values are propagated
to vendor bill lines.

See ``MIGRATION_NOTES.md`` for Odoo 20-specific changes and validation scope.
