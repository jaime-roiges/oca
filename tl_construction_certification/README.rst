TL Construction Work Certifications
===================================

.. image:: https://img.shields.io/badge/maturity-Beta-yellow.png
   :alt: Beta

.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :alt: License AGPL-3

Odoo 20 addon by **Tecniloop**. Implements cumulative work certifications,
origin invoices, customer advances, guarantee retentions, partial credit
notes and retention releases on top of the Odoo ``construction_developer``
industry module.

This is an independent Tecniloop addon, **not** an OCA-published or
OCA-maintained module. It follows OCA development conventions where
applicable. The addon also depends on Odoo Enterprise industry components.

Requirements
============

* Odoo 20 with ``construction_developer`` installed (which includes
  ``construction`` and other Enterprise dependencies).
* A sales order for the work and accounting accounts configured for advances
  (reconcilable current liability) and guarantee retentions (reconcilable
  current asset).
* Billing permissions to generate, post or reverse accounting documents.

Configuration and usage
=======================

Refer to ``readme/USAGE.md`` for a detailed workflow and to
``CHANGELOG.md`` for the changes in version 20.0.1.60.0.

Accounting safeguards
=====================

* An advance must have its invoice **posted**, even when it has no taxes,
  before it can be deducted from an origin invoice.
* A zero untaxed balance is allowed when certified work is exactly offset by
  applied advances. It is still a real invoice with work and deduction lines.
* A partial credit note does **not** cancel a certification. The remaining
  work, advances, retentions, rounding and taxes must be fully reversed.
  When a posted invoice has an existing partial credit note, complete the
  remaining credit note from Accounting first; automatic cancellation refuses
  to create another full refund.
* Amounts on confirmed advances and approved/invoiced work certifications
  are protected against direct write/import/RPC modifications.
* If a refund is itself reversed, the original certification is restored,
  provided the related advance balances can also be restored.

Known scope boundaries
======================

* Import of FIEBDC-3/BC3 budgets is **not implemented** in this addon. A
  future importer requires a specific mapping to ``construction_developer``
  work items and validated sample BC3 files. Do not present this version as
  BC3-capable.
* The enclosed automated Odoo TransactionCase tests have **not** been
  executed in a real Odoo 20 Enterprise database. Python/XML syntax and
  packaging checks are separate and are not a substitute for an installation
  and functional accounting validation on staging.
* The ``construction_developer`` module itself was not included among the
  supplied ZIP files; only ``construction`` was supplied as a reference.

Credits
=======

Author and maintainer: Tecniloop. AGPL-3.0-or-later.

Joint BC3 economic integration
==============================

When ``tl_construction_bc3`` is also installed, CI, GG, BI and negative BAJA
are normal contracted sale lines and must be included in cumulative work
certifications at their period progress ratio. Negative price lines are
invoiced (and preserved with their sign in net-origin values). Empty BC3
drafts cannot be approved. A company may opt into restricted approval via
its Construction settings; the default ``open`` policy preserves the existing
sales team workflow until the administrator configures authorised approvers.
