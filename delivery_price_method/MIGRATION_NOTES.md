# Migration notes - delivery_price_method 19.0 -> 20.0

## Main compatibility change

Odoo 19's addon temporarily wrote `delivery.carrier.delivery_type` to `fixed` or
`base_on_rule` in `rate_shipment()` and restored it afterwards. In Odoo 20 this is
unsafe because core `delivery.carrier.write()` clears `allow_cash_on_delivery` whenever
`delivery_type` is present in the write values. The old implementation also had an open
OCA bug where an exception could leave `delivery_type` permanently changed.

The Odoo 20 migration therefore does **not write `delivery_type` at all**. It dispatches
to the core `fixed_rate_shipment()` / `base_on_rule_rate_shipment()` methods directly and
reuses the Odoo 20 tax, margin and free-over processing semantics locally.

## Views

- `delivery.view_delivery_carrier_form` still exists in Odoo 20.
- `integration_level` still exists and is used as the anchor for `price_method`.
- The core pricing tab is now targeted explicitly as `page[@name='pricing']` instead of
  relying on `(//page)[1]`.

## Tests

The OCA 19 test suite was retained and an Odoo 20 regression test was added to verify
that forced local pricing does not mutate `delivery_type` or clear Cash on Delivery.

## Runtime validation still required

Static checks do not execute an Odoo server. Test on a real Odoo 20 database with at
least one external carrier provider, covering quotation rate calculation, free-over,
shipment creation, tracking number preservation, fixed local price, and rule-based local
price.
