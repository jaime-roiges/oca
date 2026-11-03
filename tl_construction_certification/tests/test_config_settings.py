from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import configure_construction_accounts


@tagged("post_install", "-at_install")
class TestConstructionSettings(TransactionCase):
    def test_settings_write_to_company(self):
        company = configure_construction_accounts(self.env)
        advance = company.construction_advance_account_id
        retention = company.construction_retention_account_id
        settings = self.env["res.config.settings"].create({"company_id": company.id})
        self.assertEqual(settings.construction_advance_account_id, advance)
        self.assertEqual(settings.construction_retention_account_id, retention)
        settings.write({"construction_retention_account_id": False})
        self.assertFalse(company.construction_retention_account_id)
        settings.write({"construction_retention_account_id": retention.id})
        self.assertEqual(company.construction_retention_account_id, retention)

    def test_spanish_settings_view(self):
        view = self.env.ref(
            "tl_construction_certification.res_config_settings_view_form_construction"
        ).with_context(lang="es_ES")
        arch = etree.fromstring(view.arch_db.encode())
        self.assertTrue(arch.xpath("//block[@title='Contabilidad de obra']"))
        self.assertTrue(arch.xpath("//setting[@string='Cuentas de obra']"))
        fields_info = self.env["res.config.settings"].with_context(lang="es_ES").fields_get(
            allfields=["construction_advance_account_id", "construction_retention_account_id"],
            attributes=["string"],
        )
        self.assertEqual(fields_info["construction_advance_account_id"]["string"], "Cuenta de anticipos de obra")
        self.assertEqual(fields_info["construction_retention_account_id"]["string"], "Cuenta de retenciones de obra")
