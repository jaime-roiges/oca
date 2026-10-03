=====================
Delivery Price Method
=====================

This module allows forcing a local price calculation for any delivery method,
including carriers whose normal rate is obtained from a web service. The local
calculation can use Odoo's fixed price or pricing rules while the real carrier
continues to handle shipment creation and tracking.

Usage
=====

#. Go to *Sales > Configuration > Sales Orders > Delivery Methods*.
#. Open an integration delivery method.
#. Select *Carrier obtained price*, *Fixed price* or *Based on Rules* in
   *Price method*.
#. Configure the fixed price or pricing rules when a local method is selected.
