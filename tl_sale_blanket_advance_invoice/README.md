# Blanket Contract - Customer Fiscal Advance Invoice

Odoo 20 customer advance VAT invoice wizard on `sale.blanket.order`.

* Company 438 account (`liability_current`) must be configured in the existing
  `tl_sale_advance_allocation` settings.
* Choose taxable base and sales tax (Spanish VAT as applicable).
* Draft invoice is created with 438 credit and the VAT account; its record is
  registered in `tl.sale.advance`.
* Accountant posts, charges and reconciles the invoice; subsequent deliveries
  allocate its outstanding tax base through the pre-existing allocation addon.
* Supplier-side fiscal advances rely on the OCA `purchase_deposit` addon and
  the vendor's legally issued tax invoice, not on this customer wizard.

Automatic allocation remains disabled by default. Test 438/407, partial
invoicing, reversals and SII/VeriFactu where applicable.
