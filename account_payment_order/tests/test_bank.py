# © 2017 Creu Blanca
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError

from odoo.addons.base.tests.common import BaseCommon


class TestBank(BaseCommon):
    def test_bank(self):
        bank = self.env["res.partner.bank"].search(
            [("bank_bic", "!=", False)], limit=1
        )
        if not bank:
            bank = self.env["res.partner.bank"].create(
                {
                    "account_number": "FR7612345678901234567890123",
                    "partner_id": self.env.company.partner_id.id,
                    "bank_name": "Fiducial Banque",
                    "bank_bic": "FIDCFR21XXX",
                    "street": "38 rue Sergent Michel Berthet",
                    "zip": "69009",
                    "city": "Lyon",
                    "country_id": self.env.ref("base.fr").id,
                }
            )
        with self.assertRaises(ValidationError):
            bank.bank_bic = "TEST"
