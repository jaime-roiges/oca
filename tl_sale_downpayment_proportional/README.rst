========================================
Sale Down Payment Proportional Deduction
========================================

This module implements a **proportional deduction of standard down-payment
invoices** when the sales order is billed in multiple invoices in Odoo 20.

It is a Tecniloop addon following OCA conventions. It is NOT a port or a copy
of ``OCA/sale-workflow/sale_advance_payment``: that OCA module deals with
recording advance **payments** and applying them to invoices. The Odoo core
model ``sale.advance.payment.inv`` produces native advance **invoices**, which
are the source of this module's negative deduction lines.

Configuration
=============

No special configuration. Install the module alongside the standard ``sale``
addon. When creating an invoice for a sales order, select **Deduct down
payments** as usual. Unticking that box preserves the standard behaviour of
not deducting down payments.

Usage example
=============

* SO base: 10,000; standard advance invoice: 30% = 3,000 (tax excluded).
* First bill: products 2,000; advance deducted 600; net billed 1,400.
* Second bill: products 3,000; advance deducted 900; net billed 2,100.
* Third bill: products 5,000; advance deducted 1,500; net billed 3,500.

The advance invoice itself is not changed. It should be validated and paid in
Odoo through the standard accounting flow. This addon follows Odoo's standard
eligibility criteria for invoice deduction: it does not itself verify the
payment status of the advance invoice.

Technical details
=================

* A dedicated override of ``sale.order._create_account_invoices`` executes
  after standard invoice grouping and before final posting/refund conversion.
* Only invoice lines with ``is_downpayment=True`` and a negative quantity are
  modified. The original positive advance invoice and sale lines remain intact.
* Original advance credit and previous consumption are obtained from linked
  non-cancelled customer invoices/refunds in the *sales order currency*.
* Target deduction = advance base x current invoiced product base / SO base,
  capped at available credit and current product base (both net and gross). On the final invoice,
  any remaining rounding difference is cleared up to the current product base.
* ``quantity=-1`` is retained, while ``price_unit`` and the Odoo 20
  ``extra_tax_data`` manual amounts are scaled together. This protects cents
  from product-quantity precision and retains tax repartition information.
* Invoices consolidated from several sales orders are allocated separately.
* A PostgreSQL row lock on the SO serializes concurrent ``final=True`` invoice
  creation, preventing concurrent deductions of the same credit.

Limitations / validation
========================

* This addon only affects **native sales-order down-payment invoice lines**;
  it does not allocate customer account payments, bank reconciliations, or OCA
  ``sale_advance_payment`` payments.
* No change is made retroactively to invoices already generated/posted.
* Sales orders with zero/negative untaxed base, or invoice lines mixing
  multiple sale orders in the same product line, are rejected with a clear
  message instead of guessing an allocation.
* Keep the original advance invoice and subsequent invoices in the same
  currency and company; a differing currency on a generated invoice is rejected.
* Exotic tax structures, multi-rate advances, credit notes, manual edits,
  tax-inclusive pricing and Spanish localization should be regression-tested
  in the target database before production use. The supplied Odoo integration
  tests run only in an Odoo 20 installation with PostgreSQL.
* Previous draft invoices reserve part of the advance (matching Odoo's
  standard invoicing policy); cancel a draft to release the amount.

Development / testing
=====================

The source follows OCA's minimal addon structure and AGPL-3.0 licensing.
Run the integration suite on a disposable Odoo 20 database::

   odoo-bin -d <test_db> --stop-after-init --test-enable \
       --test-tags /tl_sale_downpayment_proportional \
       -i tl_sale_downpayment_proportional

This command is an example; adjust binary/configuration/addons path and
installation state to your environment. Never run tests against production.

References
==========

* Odoo 20 ``addons/sale/models/sale_order.py``: ``_create_invoices`` and
  ``_create_account_invoices``.
* Odoo 20 ``addons/sale/models/sale_order_line.py``: downpayment
  ``_prepare_invoice_line`` and ``_prepare_qty_invoiced``.
* Odoo 20 ``addons/account/models/account_tax.py``:
  ``_reverse_quantity_base_line_extra_tax_data`` and manual tax values.
* OCA sale-workflow 19.0 ``sale_advance_payment`` (conceptual reference only).

Credits
=======

**Author:** Tecniloop, 2026.

**License:** AGPL-3.0 or later.
