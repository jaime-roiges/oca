from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBaseVatCompat(TransactionCase):
    def test_vies_api_is_available(self):
        Partner = self.env["res.partner"]
        self.assertIn("vies_valid", Partner._fields)
        self.assertIn("perform_vies_validation", Partner._fields)
        self.assertTrue(hasattr(Partner, "_check_vies_validity_iap"))
        self.assertTrue(hasattr(Partner, "_check_vies_iap"))
        self.assertTrue(hasattr(Partner, "_cron_check_vies_validity_iap"))
        self.assertTrue(hasattr(Partner, "_cron_check_vies_iap"))
        self.assertIn("has_foreign_fiscal_position", self.env["res.country"]._fields)
        self.assertIn("vat_check_vies", self.env["res.company"]._fields)
        self.assertIn("vat_check_vies", self.env["res.config.settings"]._fields)

    def test_legacy_xmlids(self):
        self.assertTrue(self.env.ref("base_vat.view_partner_base_vat_form"))
        self.assertTrue(self.env.ref("base_vat.res_config_settings_view_form"))
        self.assertEqual(
            self.env.ref("base_vat.vies_iap_check_update"),
            self.env.ref("l10n_eu_account_vies.vies_iap_check_update"),
        )
