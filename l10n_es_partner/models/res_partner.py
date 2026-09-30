# Copyright 2009 Jordi Esteve
# Copyright 2012-2014 Ignacio Ibeas
# Copyright 2016 Tecnativa - Carlos Dauden
# Copyright 2016,2022,2025 Tecnativa - Pedro M. Baeza
# Copyright 2025 Studio73 - Pablo Cortes
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    comercial = fields.Char("Trade name", size=128, index="trigram")

    @api.depends("comercial")
    @api.depends_context("no_display_commercial")
    def _compute_display_name(self):
        super(
            ResPartner,
            self.with_context(
                display_commercial=not self.env.context.get(
                    "no_display_commercial", False
                )
            ),
        )._compute_display_name()
        name_pattern = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_str("l10n_es_partner.name_pattern", default="")
        )
        if not name_pattern:
            return
        for partner in self:
            if partner.comercial and partner.env.context.get("formatted_display_name"):
                partner.display_name = name_pattern % {
                    "name": partner.display_name,
                    "comercial_name": partner.comercial,
                }

    def _get_complete_name(self):
        name = super()._get_complete_name()
        if self.env.context.get("display_commercial") and self.comercial:
            name_pattern = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_str("l10n_es_partner.name_pattern", default="")
            )
            if name_pattern:
                name = name_pattern % {
                    "name": name,
                    "comercial_name": self.comercial,
                }
        return name

    @api.depends("comercial")
    def _compute_complete_name(self):
        super()._compute_complete_name()
        for partner in self:
            partner.complete_name = partner.with_context(
                display_commercial=not self.env.context.get(
                    "no_display_commercial", False
                )
            )._get_complete_name()

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + ["comercial"]

    @api.model
    @api.readonly
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        rec_names = list(self._rec_names_search)
        if "comercial" not in rec_names:
            self._rec_names_search = [*rec_names, "comercial"]
        return super().name_search(
            name=name, domain=domain, operator=operator, limit=limit
        )
