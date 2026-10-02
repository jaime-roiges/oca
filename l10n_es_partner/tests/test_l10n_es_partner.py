# Copyright 2016-2017 Tecnativa - Pedro M. Baeza
# Copyright 2017 Tecnativa - Carlos Dauden <carlos.dauden@tecnativa.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3).

from odoo.tests import common


class TestL10nEsPartner(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_str(
            "l10n_es_partner.name_pattern", ""
        )
        cls.country_spain = cls.env.ref("base.es")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Empresa de prueba",
                "comercial": "Nombre comercial",
                "vat": "ES12345678Z",
                "country_id": cls.country_spain.id,
            }
        )
        cls.env.user.company_id.country_id = cls.country_spain.id

    def test_search_commercial(self):
        partner_obj = self.env["res.partner"]
        self.assertIn(
            self.partner.id, map(lambda x: x[0], partner_obj.name_search("prueba"))
        )
        self.assertNotIn(
            self.partner.id,
            map(
                lambda x: x[0], partner_obj.name_search("prueba", operator="not ilike")
            ),
        )
        self.assertIn(
            self.partner.id, map(lambda x: x[0], partner_obj.name_search("comercial"))
        )
        self.assertNotIn(
            self.partner.id,
            map(
                lambda x: x[0],
                partner_obj.name_search("comercial", operator="not ilike"),
            ),
        )

    def test_partner_bank_extra_fields(self):
        bank = self.env["res.partner.bank"].create(
            {
                "account_number": "1234567890",
                "partner_id": self.partner.id,
                "bank_name": "Banco de prueba",
                "bank_long_name": "Banco de prueba, S.A.",
                "bank_vat": "ESA00000000",
                "bank_website": "https://example.com",
            }
        )
        self.assertEqual(bank.bank_long_name, "Banco de prueba, S.A.")
        self.assertEqual(bank.bank_vat, "ESA00000000")
        self.assertEqual(bank.bank_website, "https://example.com")

    def test_name(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "l10n_es_partner.name_pattern", "%(comercial_name)s (%(name)s)"
        )
        partner2 = self.env["res.partner"].create(
            {
                "name": "Empresa de prueba",
                "comercial": "Nombre comercial",
                "street": "My street",
            }
        )
        self.assertEqual(partner2.display_name, "Nombre comercial (Empresa de prueba)")
        self.assertEqual(partner2.complete_name, "Nombre comercial (Empresa de prueba)")
        self.assertEqual(
            partner2.with_context(show_address=True).display_name,
            "Nombre comercial (Empresa de prueba)\nMy street",
        )
        partner2.with_context(
            show_address=True, display_commercial=True
        )._compute_complete_name()
        partner2.write({"comercial": "Nuevo nombre"})
        self.assertEqual(partner2.display_name, "Nuevo nombre (Empresa de prueba)")
        self.assertEqual(partner2.complete_name, "Nuevo nombre (Empresa de prueba)")
        self.assertEqual(
            partner2.with_context(no_display_commercial=True).display_name,
            "Empresa de prueba",
        )
        self.assertEqual(partner2.display_name, "Nuevo nombre (Empresa de prueba)")
