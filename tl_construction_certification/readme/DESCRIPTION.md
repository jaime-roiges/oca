This module adds Work Certifications (*Certificaciones de Obra*) and Origin Invoicing (*Facturación a Origen*) on top of the official Odoo Construction / Property Developer industry module.

It allows measuring work progress periodically against the sales order budget (using the hierarchical line structure already present in `construction_developer`) and generating customer invoices that show the cumulative certified amount from the origin of the contract, the previously invoiced amount, and the amount to invoice for the current period.

Additional features:
- Guarantee retentions (retenciones de garantía) with configurable percentage.
- Construction advances (anticipos). The amount is a tax-excluded base. Taxes default from the budget and are invoiced on the advance, then reversed on the origin invoice. The advance liability is reconcilable and is matched when both invoices are posted. Each application is a ledger row. Raising the applied total adds the difference on the oldest pending advance and does not move a line already chosen; lowering it takes the difference from the latest advances. Cancelling the certification keeps the row but frees the balance. A cancelled advance cannot be revived by reopening the certification.
- Guarantee retention posted to a current-asset account, not to income. A normal certification can only reduce the retention it withholds in the period. Paying it back is a liquidation, and the balance still held cannot be released twice.
- Origin amounts count only approved and invoiced certifications. An invoiced or approved certification keeps the amounts it was closed with until it is reset to draft. The certified price is the tax-excluded net of the sales discount. The period amount absorbs the last cent so the parts of a budget add up to the budget. A date cannot be placed before a later approved or invoiced certification, and certified quantities plus what the sales order already invoiced cannot exceed the budget. Cancelling a posted invoice is limited to billing users and creates a credit note that keeps the certified price and accounts; a payment already collected is left in place. The uncertified remainder of a line stays on the sales order invoice. An advance with taxes has to be invoiced before it is deducted.
- Deeper integration with the MRP Delivery Progress (`x_cumulated_qty` / `x_cumulated_percent`) to propose quantities and display current physical progress.
- Printable Work Certification PDF report.
- Specific *Origin Invoice* PDF report with full origin breakdown.
- Dedicated *Retention Liquidation* PDF report.
