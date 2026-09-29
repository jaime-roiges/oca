# Copyright 2017 Tecnativa - Carlos Dauden
# Copyright 2022,2024 Tecnativa - Pedro M. Baeza
# Copyright 2026 Migration to Odoo 20
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3).

from odoo.tests import Form, common


class TestBaseBankFromIban(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Tecnativa, S.L",
                "vat": "ES12345678Z",
                "country_id": cls.env.ref("base.es").id,
            }
        )
        cls.bank_obj = cls.env["res.partner.bank"].with_context(
            default_partner_id=cls.partner.id
        )

    def test_onchange_iban(self):
        partner_bank = Form(self.bank_obj)
        partner_bank.account_number = "DE89370400440532013000"
        self.assertEqual(partner_bank.account_type, "iban")
        self.assertEqual(partner_bank.bank_name, "Commerzbank")
        self.assertEqual(partner_bank.bank_bic, "COBADEFFXXX")
        self.assertEqual(partner_bank.bank_code, "37040044")
        self.assertEqual(partner_bank.country_id, self.env.ref("base.de"))

    def test_create_iban_found(self):
        partner_bank = self.env["res.partner.bank"].create(
            {
                "account_number": "DE89370400440532013000",
                "partner_id": self.partner.id,
            }
        )
        self.assertEqual(partner_bank.bank_name, "Commerzbank")
        self.assertEqual(partner_bank.bank_bic, "COBADEFFXXX")
        self.assertEqual(partner_bank.bank_code, "37040044")
        self.assertEqual(partner_bank.country_id, self.env.ref("base.de"))

    def test_create_invalid_account_number(self):
        partner_bank = self.env["res.partner.bank"].create(
            {
                "account_number": "1234567890",
                "partner_id": self.partner.id,
            }
        )
        self.assertFalse(partner_bank.bank_name)
        self.assertFalse(partner_bank.bank_bic)
        self.assertFalse(partner_bank.bank_code)

    def test_explicit_bank_data_is_preserved(self):
        partner_bank = self.env["res.partner.bank"].create(
            {
                "account_number": "DE89370400440532013000",
                "partner_id": self.partner.id,
                "bank_name": "Manual Bank Name",
            }
        )
        self.assertEqual(partner_bank.bank_name, "Manual Bank Name")
        self.assertEqual(partner_bank.bank_bic, "COBADEFFXXX")
