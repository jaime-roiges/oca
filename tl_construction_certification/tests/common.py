# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def configure_construction_accounts(env):
    """Create the liability and asset accounts the origin invoice posts to."""
    company = env.company
    if company.construction_advance_account_id and company.construction_retention_account_id:
        return company
    account_model = env["account.account"]
    if not company.construction_advance_account_id:
        company.construction_advance_account_id = account_model.create({
            "name": "Customer construction advances",
            "code": "438001",
            "account_type": "liability_current",
            "reconcile": True,
            "company_ids": [(6, 0, [company.id])],
        })
    if not company.construction_retention_account_id:
        company.construction_retention_account_id = account_model.create({
            "name": "Guarantee retentions",
            "code": "449001",
            "account_type": "asset_current",
            "reconcile": True,
            "company_ids": [(6, 0, [company.id])],
        })
    return company


def mark_invoiced(certification):
    """Attach a draft invoice and mark the certification invoiced.

    The state is refused without an invoice, including from tests.
    """
    certification.ensure_one()
    journal = certification.env["account.journal"].search([
        ("type", "=", "sale"),
        ("company_id", "=", certification.company_id.id),
    ], limit=1)
    vals = {
        "move_type": "out_invoice",
        "partner_id": certification.partner_id.id,
        "invoice_date": certification.date,
        "invoice_line_ids": [(0, 0, {
            "name": certification.name or "Certification",
            "quantity": 1.0,
            "price_unit": abs(certification.amount_final_to_invoice or 0.0) or 1.0,
        })],
    }
    if journal:
        vals["journal_id"] = journal.id
    invoice = certification.env["account.move"].create(vals)
    certification.write({"invoice_id": invoice.id, "state": "invoiced"})
    return invoice
