from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _check_vies_iap(self):
        """Compatibility name used by base_vat up to Odoo 19."""
        return self._check_vies_validity_iap()

    @api.model
    def _cron_check_vies_iap(self):
        """Compatibility name used by the Odoo 19 base_vat cron."""
        return self._cron_check_vies_validity_iap()
