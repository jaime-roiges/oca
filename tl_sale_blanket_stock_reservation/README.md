# Blanket Contracts - Dedicated Stock Locations

Odoo 20 addon extending OCA `sale_blanket_order` with separated, **internal**
locations for stock commercially dedicated to a specific customer contract
line. Goods remain owned and valued by the selling company.

* Choose a warehouse on the contractual line, generate dedicated location.
* Move purchased/normal stock to the protected location via standard internal
  transfer; warehouse staff must confirm physically with PDA.
* For linked purchase orders with unequivocal products, receipt proposes an
  internal transfer. Multi-step receiving may need manual allocation.
* Delivery procurement sources goods from the dedicated location when the
  warehouse source rule matches the standard stock location.
* Check physical stock at sale confirmation; block wrong-contract deliveries.

Test one-, two- and three-step picking routes and location security before use.
