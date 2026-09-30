============================
Purchase Delivery Split Date
============================

This OCA addon makes confirmed Purchase Orders generate one incoming shipment per
scheduled date. Changes to scheduled dates on confirmed Purchase Order lines reorganize
pending stock moves so each incoming shipment contains moves for a single date.

Odoo 20 migration
=================

The Odoo 20 purchase/stock flow assigns pickings after creating purchase moves. This
migration therefore adds the planned receipt date to ``stock.move._key_assign_picking``
and follows ``stock.move.date`` when a Purchase Order line planned date changes.

Original project: https://github.com/OCA/purchase-workflow
License: AGPL-3.0-or-later.
