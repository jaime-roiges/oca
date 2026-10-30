1. Open a confirmed Sales Order that is linked to a project (as managed by the Property Developer module).
2. Click the **Create Certification** button in the header.
3. Choose the certification date and whether to import the current cumulative progress from the linked Manufacturing Orders (uses `x_cumulated_qty` from Delivery Progress).
4. Review and adjust the quantities / percentages for the current period on each budget line. MRP cumulative progress is shown as reference.
5. Set the retention percentage if different from the default (5%).
6. On the company form, set the advance account (current liability) and the retention account (current asset). Both must belong to that company. They are marked reconcilable. They are required before invoicing an advance, a retention or a liquidation.
7. Optionally apply pending advances with **Apply Pending Advance**, or edit the lines on the **Advances** tab. Raising the total adds the difference without moving those lines. Lowering it removes the difference from the newest advances. The advance amount is the tax-excluded base; its taxes are reversed on this invoice.
8. Confirm the measurement and approve the certification. Approved lines are locked, and the approved amounts stay as they were. Reset the certification to draft if an earlier one was cancelled and the origin has to be calculated again.
9. Click **Create Invoice (Origin)** (billing users). The customer pays the net amount plus VAT on the certified base. Retention is outside VAT. An advance is deducted with the taxes of its posted invoice, so the advance invoice must be posted **even if there is no VAT**. Cancelling a certification that already has an invoice is also limited to billing users: a draft invoice is cancelled and a posted one is fully reversed without undoing a payment already collected. If there are existing partial credit notes, complete the remaining refund in Accounting first: cancelling the certification directly is deliberately blocked. The uncertified remainder of a budget line stays available on the sales order. What is already on a certification is not invoiced from there.
10. Print the **Work Certification** report (PDF). A stored ratio of 0.5 is printed as 50%.

**Advances**: Create advances from the Sales menu or from the Sales Order. Confirm them and generate the advance invoice. It credits the advance liability, not income, and adds the advance taxes on top of the base. Apply them on a draft or measured certification. **Apply Pending Advance** only adds what is still missing up to the net amount; it does not reshuffle lines you already chose. A posted advance invoice is reversed if the advance is cancelled.

**Retention Liquidation**:
- On a normal certification, *Retention to Release* can only reduce the retention withheld in this period.
- Mark *Retention Liquidation* to pay back retention already invoiced. The amount cannot exceed the balance still held, so the same retention cannot be released twice.

**Origin Invoice Report**: When printing an invoice that comes from a certification, use the *Origin Invoice* report to get the full origin breakdown (certified, previously invoiced, retention, advances, final amount).

**Retention Liquidation Report**: Print the *Retention Liquidation* report from a certification to obtain a dedicated summary focused on the retention release (full or partial).

You can also access all certifications from the Sales menu or from the smart buttons on the Sales Order and Project forms.

**Partial refunds and re-certification:** Posted partial credit notes linked to certification lines release those quantities in the available budget; the next certification wizard proposes the remaining measured progress using the net (not gross) certified quantities. A credit note that does not include all original adjustments does not cancel a certification. Reversing a complete credit note restores the original certified position if no new advance application conflicts with it.

**BC3 / FIEBDC-3:** No BC3 importer is included in this version.
