# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestCreditCheckout(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_partner = cls.env["res.partner"].create({
            "name": "Dimpal trade customer",
            "is_company": True,
            "skip_website_checkout_payment": True,
        })
        cls.other_partner = cls.env["res.partner"].create({
            "name": "Other B2B partner",
            "is_company": True,
        })

    def test_credit_authorization_flag_is_explicit(self):
        self.assertTrue(self.company_partner.skip_website_checkout_payment)
        self.assertFalse(self.other_partner.skip_website_checkout_payment)

    def test_website_cart_is_never_automatic_call_off(self):
        website = self.env["website"].search([], limit=1)
        if not website:
            self.skipTest("No website available")
        # The OCA-generated release wizard, not this cart, creates call-off orders.
        vals = website._prepare_sale_order_values(self.company_partner)
        self.assertFalse(vals["create_call_off_from_so_if_possible"])
