from odoo.tests.common import TransactionCase


class TestL10nEsPartner(TransactionCase):
    def test_trade_name_field(self):
        partner = self.env["res.partner"].create({
            "name": "Empresa Demo",
            "is_company": True,
            "comercial": "Marca Demo",
        })
        self.assertEqual(partner.comercial, "Marca Demo")

    def test_bank_extra_fields(self):
        partner = self.env["res.partner"].create({"name": "Empresa Demo"})
        bank = self.env["res.partner.bank"].create({
            "partner_id": partner.id,
            "account_number": "ES9121000418450200051332",
            "bank_name": "Banco Demo",
            "bank_long_name": "Banco Demo Sociedad Anonima",
            "bank_vat": "A00000000",
            "bank_website": "https://example.com",
        })
        self.assertEqual(bank.bank_name, "Banco Demo")
        self.assertEqual(bank.bank_vat, "A00000000")
