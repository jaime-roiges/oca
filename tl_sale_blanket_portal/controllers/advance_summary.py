# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Fiscal advance ledger exposed to authorised customers in their own portal.

Do not derive the commercial advance from the account receivable residual or
from tax-inclusive invoice totals. Advance consumption is the taxable base of
allocations, split between draft and posted delivery invoices. A payment in
progress is not treated as reconciled/paid.
"""


def advance_portal_summary(advances, currency):
    """Return a customer-safe, VAT-exclusive snapshot for ONE blanket contract.

    Only posted customer advance invoices belong in the fiscal ledger. A draft
    target invoice reserves a part of the paid advance but must not be shown as
    a definitive, posted application. Cancelled targets do not consume it.
    """
    summary = {
        "invoiced": 0.0,
        "fully_paid": 0.0,
        "posted_applied": 0.0,
        "draft_reserved": 0.0,
        "available": 0.0,
        "awaiting_payment": 0.0,
        "rows": [],
    }
    for advance in advances:
        if advance.kind != "customer" or advance.invoice_id.state != "posted":
            continue
        paid = advance.invoice_id.payment_state == "paid"
        base = currency.round(advance.amount_base)
        allocations = []
        posted = draft = 0.0
        for allocation in advance.allocation_ids:
            invoice = allocation.invoice_id
            if invoice.state not in ("draft", "posted"):
                continue
            amount = currency.round(allocation.amount_base)
            if invoice.state == "posted":
                posted += amount
            else:
                draft += amount
            allocations.append({
                "invoice_name": invoice.name if invoice.name and invoice.name != "/" else invoice.ref or "/",
                "invoice_date": invoice.invoice_date,
                "state": invoice.state,
                "amount": amount,
            })
        posted = currency.round(posted)
        draft = currency.round(draft)
        # Unpaid advances cannot be newly applied, but previously posted
        # applications remain visible in the historical fiscal ledger.
        available = currency.round(max(0.0, base - posted - draft)) if paid else 0.0
        summary["invoiced"] += base
        summary["fully_paid"] += base if paid else 0.0
        summary["posted_applied"] += posted
        summary["draft_reserved"] += draft
        summary["available"] += available
        summary["awaiting_payment"] += 0.0 if paid else base
        summary["rows"].append({
            "invoice_name": advance.invoice_id.name if advance.invoice_id.name and advance.invoice_id.name != "/" else advance.invoice_id.ref or "/",
            "invoice_date": advance.invoice_id.invoice_date,
            "payment_state": advance.invoice_id.payment_state,
            "base": base,
            "paid": paid,
            "posted_applied": posted,
            "draft_reserved": draft,
            "available": available,
            "allocations": allocations,
        })
    for key in ("invoiced", "fully_paid", "posted_applied", "draft_reserved", "available", "awaiting_payment"):
        summary[key] = currency.round(summary[key])
    return summary
