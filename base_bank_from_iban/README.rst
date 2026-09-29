==============
Bank from IBAN
==============

Odoo 20 migration of ``base_bank_from_iban``.

This module enriches ``res.partner.bank`` directly from an IBAN using
``schwifty``. Odoo 20 removed the standalone ``res.bank`` model, so bank
metadata is now written to the bank account itself.

Filled fields
=============

* Bank Name (``bank_name``)
* BIC/SWIFT (``bank_bic``)
* Country (``country_id``)
* Bank Code (``bank_code``; supplied by this addon)

Explicitly entered values are preserved; the lookup only fills missing data.

Migration
=========

See ``MIGRATION_NOTES.md`` for the Odoo 19 -> 20 architectural changes.

License
=======

AGPL-3.0 or later.
