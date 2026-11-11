# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from types import SimpleNamespace as NS

from odoo.tests.common import TransactionCase

from ..controllers.advance_summary import advance_portal_summary


class TestPortalAdvanceSummary(TransactionCase):
    def _invoice(self, state, payment_state="not_paid", name="INV", date=None):
        return NS(state=state, payment_state=payment_state, name=name, ref=False, invoice_date=date)

    def _advance(self, base, payment="paid", applications=(), state="posted"):
        return NS(
            kind="customer", invoice_id=self._invoice(state, payment), amount_base=base,
            allocation_ids=[NS(invoice_id=self._invoice(st, name=name), amount_base=amount)
                            for st, amount, name in applications],
        )

    def test_paid_advance_split_posted_draft_cancelled(self):
        currency = self.env.company.currency_id
        advance = self._advance(1000, applications=[
            ("posted", 300, "FV/001"),
            ("draft", 200, "/"),
            ("cancel", 70, "FV/CANCEL"),
        ])
        result = advance_portal_summary([advance], currency)
        self.assertEqual(result["posted_applied"], 300)
        self.assertEqual(result["draft_reserved"], 200)
        self.assertEqual(result["available"], 500)
        self.assertEqual(len(result["rows"][0]["allocations"]), 2)

    def test_unpaid_or_draft_advance_not_available(self):
        currency = self.env.company.currency_id
        paid = self._advance(250)
        unpaid = self._advance(350, payment="partial")
        draft = self._advance(500, state="draft")
        result = advance_portal_summary([paid, unpaid, draft], currency)
        self.assertEqual(result["available"], 250)
        self.assertEqual(result["fully_paid"], 250)
        self.assertEqual(result["awaiting_payment"], 350)
        self.assertEqual(result["invoiced"], 600)
        self.assertEqual(len(result["rows"]), 2)

    def test_vendor_advances_never_appear_in_customer_portal(self):
        currency = self.env.company.currency_id
        vendor = self._advance(900)
        vendor.kind = "supplier"
        self.assertEqual(advance_portal_summary([vendor], currency)["available"], 0)
