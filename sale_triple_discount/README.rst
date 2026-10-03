====================
Sale Triple Discount
====================

This module adds three successive discounts to sale order lines while keeping Odoo's
standard ``discount`` field as the exact effective discount used by taxes and totals.

The Odoo 20 port keeps the OCA 17.0 additive and multiplicative modes. Multiplicative
components are propagated individually to invoice lines. Additive components are
flattened to one equivalent invoice discount because ``account_invoice_triple_discount``
models multiplicative components only; this preserves invoice amounts exactly.

Installation requires the Odoo 20 port of ``account_invoice_triple_discount``.
