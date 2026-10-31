# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import binascii
import html
import hashlib
import logging
from dataclasses import asdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.binary import BinaryValue

from ..lib.bc3_parser import Bc3Error, coefficient_amounts, parse_bc3
from ..lib.import_logic import (
    budget_key, certification_period, coefficient_origin_ratio,
    validate_budget_keys, validated_budget_total,
)

_logger = logging.getLogger(__name__)

_UOM_XMLID = {
    "m": "uom.product_uom_meter",
    "m2": "uom.product_uom_square_meter",
    "m3": "uom.product_uom_cubic_meter",
    "km": "uom.product_uom_km",
    "cm": "uom.product_uom_cm",
    "kg": "uom.product_uom_kgm",
    "g": "uom.product_uom_gram",
    "t": "uom.product_uom_ton",
    "l": "uom.product_uom_litre",
    "h": "uom.product_uom_hour",
    "d": "uom.product_uom_day",
    "u": "uom.product_uom_unit",
}
_UOM_NAMES = {
    "m2": ["m²", "m2"],
    "m3": ["m³", "m3"],
    "cm2": ["cm²", "cm2"],
    "cm3": ["cm³", "cm3"],
    "dm3": ["dm³", "dm3"],
    "ha": ["ha"],
    "a": ["a"],
    "mes": ["mes", "Mes", "Months"],
    "mu": ["mil", "Mil"],
    "cu": ["cien"],
}
_UNIT_ALIAS = {
    "ud": "u",
    "uds": "u",
    "un": "u",
    "unidad": "u",
    "unidades": "u",
    "pa": "u",
    "u": "u",
    "hora": "h",
    "horas": "h",
    "hr": "h",
    "h": "h",
    "ml": "m",
    "m2": "m2",
    "m3": "m3",
}


class Bc3ImportWizard(models.TransientModel):
    _name = "bc3.import.wizard"
    _description = "Import FIEBDC-3 BC3 file"

    data_file = fields.Binary(string="BC3 File", required=True)
    filename = fields.Char(string="Filename")
    import_mode = fields.Selection(
        selection=[
            ("auto", "Automatic"),
            ("catalog", "Product catalog"),
            ("budget", "Budget"),
            ("both", "Catalog and budget"),
        ],
        string="Import Mode",
        default="auto",
        required=True,
    )
    partner_id = fields.Many2one(comodel_name="res.partner", string="Customer")
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Sales Order",
        domain="[('state', 'in', ('draft', 'sent', 'sale', 'done'))]",
    )
    update_existing = fields.Boolean(
        string="Update existing products",
        default=False,
        help="Only updates products already tagged with the same BC3 code. "
        "Never reuses an ordinary product solely because its internal reference matches.",
    )
    import_breakdown = fields.Boolean(
        string="Import price justification",
        help="Also create products for materials, labor and machinery that "
        "only appear inside a work-item decomposition. They are not added "
        "as sales order lines.",
    )
    prefer_decomposition_price = fields.Boolean(
        string="Use decomposition price",
        default=True,
        help="Default follows FIEBDC (~D price prevails); uncheck to retain ~C "
        "contract prices. Price discrepancies are logged.",
    )
    apply_coefficients = fields.Boolean(
        string="Apply coefficients",
        help="Add indirect costs, award discount, overheads and industrial "
        "profit as extra lines. Leave it unchecked when the work-item prices "
        "already include them. VAT is never added as a line.",
    )
    create_certification = fields.Boolean(
        string="Create certification",
        default=True,
        help="When the file is a certification (information type 3) and the "
        "work-certification module is installed, create a draft certification "
        "with the measured-to-date quantities.",
    )

    validation_mode = fields.Selection(
        [("strict", "FIEBDC-3/2024 strict"),
         ("compatible", "Compatible with incomplete/legacy BC3 (warnings)")],
        string="Validation policy", default="strict", required=True,
        help="Strict mode checks ~D/~M and detailed measurement totals, and "
             "requires traceable ~M work-item measurements. Compatible mode "
             "reports inconsistencies but never silently assigns a wrong position.",
    )
    price_scope = fields.Integer(
        string="Price scope (1-based)", default=1, required=True,
        help="Price tariff index in ~C and ~K. 1 is the first listed price.",
    )
    catalog_edition = fields.Char(
        string="Source Catalog Edition",
        help="Optional explicit BC3 price-list edition (e.g. 2026-Q3). "
        "A new edition creates its own product namespace. Do not change "
        "this for routine reimports or work certificates of the same contract.",
    )
    bc3_catalog_id = fields.Many2one(
        "bc3.catalog", string="BC3 Source Catalog",
        help="Isolate identical concept codes belonging to different BC3 bases. "
             "If omitted, uses the order catalog or a catalog identified by "
             "the source document's publisher/name.",
    )

    reimport_policy = fields.Selection(
        [("update", "Update BC3 lines"), ("reject", "Reject existing BC3 lines")],
        default="update", required=True,
        string="When order already contains BC3",
        help="Update BC3-tagged lines by their hierarchical path; never duplicate them. "
        "Old lines absent from the new file block the operation.",
    )
    preview_result = fields.Text(string="BC3 Preview", readonly=True)
    allow_unknown_units = fields.Boolean(
        string="Allow unknown BC3 units",
        help="Use Units for unknown BC3 measures. Quantities/prices may not be "
        "comparable: only enable after checking the source file.",
    )

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        if self.sale_order_id:
            self.partner_id = self.sale_order_id.partner_id

    def _bc3_source_bytes(self):
        """Return the original bytes of an Odoo 20 binary upload.

        The ORM returns BinaryValue; an RPC payload can still be a base64
        string before field conversion. Never decode raw BinaryValue again.
        """
        self.ensure_one()
        payload = self.data_file
        if isinstance(payload, BinaryValue):
            return payload.content
        if isinstance(payload, str):
            return base64.b64decode(payload, validate=True)
        raise UserError(_("Invalid BC3 binary upload."))

    def _load_and_validate(self):
        """Parse and validate everything possible before the first ORM write."""
        self.ensure_one()
        if not self.data_file:
            raise UserError(_("Upload a BC3 file."))
        try:
            raw = self._bc3_source_bytes()
            if len(raw) > 40 * 1024 * 1024:
                raise Bc3Error("El BC3 supera el límite de seguridad de 40 MiB.")
            document = parse_bc3(
                raw, strict=self.validation_mode == "strict",
                price_scope=self.price_scope,
            )
            mode = self._resolve_mode(document)
            if mode == "catalog" and document.currency and (
                document.currency.upper() != self._company().currency_id.name.upper()
            ):
                raise Bc3Error(
                    "La divisa del catálogo BC3 (%s) no coincide con la moneda "
                    "de la compañía (%s). No se convierten automáticamente los precios."
                    % (document.currency, self._company().currency_id.name)
                )
            if not document.currency:
                document.warnings.append(
                    "El BC3 no declara divisa en ~K; revise la moneda del "
                    "producto/pedido antes de importar."
                )
            budget_lines = []
            if mode in ("budget", "both"):
                budget_lines = document.iter_budget_lines(self.prefer_decomposition_price)
                if not budget_lines:
                    raise Bc3Error("El BC3 carece de estructura presupuestaria.")
                validate_budget_keys(budget_lines)
                validated_budget_total(budget_lines)
                self._preflight_order(document, budget_lines)
                if not self.sale_order_id and not self.partner_id:
                    raise Bc3Error("Seleccione un cliente o un presupuesto existente.")
            return document, mode, budget_lines
        except (Bc3Error, binascii.Error) as error:
            raise UserError(str(error)) from error

    def action_preview(self):
        """Show a read-only economic preview; does not write products/orders."""
        document, mode, budget_lines = self._load_and_validate()
        items = [line for line in budget_lines if line.kind == "item"]
        subtotal = validated_budget_total(items)
        if self.sale_order_id:
            old = self.sale_order_id.order_line.filtered(lambda line: line.bc3_path)
            old_paths = set(old.mapped("bc3_path"))
        else:
            old_paths = set()
        matching = sum(budget_key(line.position) in old_paths for line in budget_lines)
        warning_lines = list(dict.fromkeys(document.warnings))
        preview = [
            "FIEBDC: %s" % (document.version or "-"),
            "Validación: %s" % self.validation_mode,
            "Ámbito de precios: %s" % self.price_scope,
            "Catálogo: %s" % (self.bc3_catalog_id.display_name or
                               self.sale_order_id.bc3_catalog_id.display_name or
                               document.property or self.filename or "BC3"),
            "Tipo: %s" % (document.info_type or "-"),
            "Modo: %s" % mode,
            "Divisa: %s" % (document.currency or "no indicada"),
            "Partidas: %s; capítulos: %s" % (
                len(items), len(budget_lines) - len(items)
            ),
            "Base material orientativa: %.2f" % subtotal,
            "Partidas/chapters con posición BC3 ya importada: %s" % matching,
            "Certificación: cantidades ~M a origen; solo se creará el período neto pendiente"
            if document.info_type == 3 else "Presupuesto: cantidades ~M o ~D",
        ]
        if warning_lines:
            preview.append("Avisos:\n- " + "\n- ".join(warning_lines[:20]))
        self.preview_result = "\n".join(preview)
        return {
            "type": "ir.actions.act_window",
            "name": _("Preview BC3 import"),
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_import(self):
        document, mode, budget_lines = self._load_and_validate()
        self._uom_cache = {}
        self._active_catalog = self._ensure_catalog(document)
        self._source_currency = document.currency
        warnings = []
        templates = self.env["product.template"]
        order = self.env["sale.order"]
        # A previously confirmed contract cannot be rewritten by certificates.
        is_certificate = (
            document.info_type == 3 and self.create_certification
            and self.sale_order_id and self.sale_order_id.state in ("sale", "done")
        )
        try:
            if not is_certificate and (
                mode in ("catalog", "both")
                or (mode == "budget" and self.import_breakdown)
            ):
                templates = self._import_catalog(document, document.catalog_concepts(), warnings)
            if mode in ("budget", "both"):
                if is_certificate:
                    order = self.sale_order_id
                    self._create_certification(order, document, budget_lines, warnings)
                else:
                    order, budget_templates = self._import_budget(
                        document, budget_lines, warnings, templates
                    )
                    templates |= budget_templates
            warnings.extend(document.warnings)
            if document.ignored:
                ignored = ", ".join(
                    "~%s (%s)" % (kind, count)
                    for kind, count in sorted(document.ignored.items())
                )
                warnings.append(_("Unimported BC3 records: %s") % ignored)
            unique_warnings = list(dict.fromkeys(warnings))
            self._archive_import(order, document, mode, unique_warnings)
            self._post_log(order, templates, document, mode, unique_warnings)
            return self._open_result(order, templates)
        except Bc3Error as error:
            raise UserError(str(error)) from error

    def _preflight_order(self, document, budget_lines):
        order = self.sale_order_id
        if not order:
            if document.info_type == 3 and self.create_certification:
                raise Bc3Error(
                    "Para importar una certificación debe seleccionar su pedido "
                    "original confirmado; no se crea un nuevo presupuesto desde una certificación."
                )
            return
        if self.partner_id and order.partner_id != self.partner_id:
            raise Bc3Error("El cliente seleccionado difiere del pedido de destino.")
        if self.bc3_catalog_id and order.bc3_catalog_id and (
            self.bc3_catalog_id != order.bc3_catalog_id
        ):
            raise Bc3Error("El catálogo seleccionado difiere del asociado al pedido.")
        if document.currency and document.currency.upper() != order.currency_id.name.upper():
            raise Bc3Error(
                "Moneda BC3 %s distinta de la moneda del pedido %s. "
                "Convierta los precios explícitamente antes de importar."
                % (document.currency, order.currency_id.name)
            )
        if document.info_type == 3 and self.create_certification:
            if order.state not in ("sale", "done"):
                raise Bc3Error(
                    "Confirme el pedido original antes de importar la certificación."
                )
            if "construction.certification" not in self.env:
                raise Bc3Error(
                    "Instale tl_construction_certification para importar certificaciones."
                )
            if not document.certification_number or document.certification_number < 1:
                raise Bc3Error("La certificación BC3 necesita NÚMERO CERTIFICACIÓN positivo en ~V.")
            return
        if order.state not in ("draft", "sent"):
            raise Bc3Error("Solo se pueden actualizar presupuestos en borrador.")
        current = order.order_line.filtered(lambda line: line.bc3_path)
        legacy_present = order.order_line.filtered(
            lambda line: line.bc3_code and not line.bc3_path
        )
        if (current or legacy_present) and self.reimport_policy == "reject":
            raise Bc3Error("El pedido contiene líneas BC3: seleccione Actualizar.")
        # Do not silently keep removed work items/coefficients from a prior BC3.
        actual_paths = {budget_key(line.position) for line in budget_lines}
        if self.apply_coefficients:
            actual_paths.update({"coefficients", "coef:CI", "coef:BAJA", "coef:GG", "coef:BI"})
        stale = current.filtered(lambda line: line.bc3_path not in actual_paths)
        if stale:
            raise Bc3Error(
                "El nuevo BC3 elimina partidas existentes (%s). "
                "Revise y elimínelas manualmente antes de reimportar."
                % ", ".join(stale.mapped("bc3_path")[:10])
            )

    def _resolve_mode(self, document):
        if self.import_mode != "auto":
            return self.import_mode
        if document.info_type in (1, 4):
            return "catalog"
        if document.info_type in (2, 3):
            return "budget"
        if document.root_concept() and any(
            concept.is_chapter for concept in document.concepts.values()
        ):
            return "budget"
        return "catalog"

    def _ensure_catalog(self, document):
        """Reuse a chosen source catalog; never globally key on concept code."""
        self.ensure_one()
        company = self._company()
        order_catalog = self.sale_order_id.bc3_catalog_id if self.sale_order_id else False
        catalog = self.bc3_catalog_id or order_catalog
        if catalog:
            if self.catalog_edition and catalog.edition != self.catalog_edition.strip():
                raise UserError(_(
                    "Selected BC3 catalog edition differs from the import edition. "
                    "Choose the matching catalog or clear Source Catalog Edition."
                ))
            if catalog.company_id != company:
                raise UserError(_("BC3 catalog belongs to another company."))
            if order_catalog and catalog != order_catalog:
                raise UserError(_("BC3 catalog differs from the one assigned to this order."))
            return catalog
        label = (document.property or document.header or self.filename or "BC3").strip()
        edition = (self.catalog_edition or "").strip()
        if edition:
            # Keep the historical UNIQUE(company, name) constraint intact on
            # existing Odoo 20 databases; an explicit edition creates a new
            # namespace without renaming old catalogs or merging products.
            label = "%s [edition: %s]" % (label, edition)
        catalog = self.env["bc3.catalog"].search([
            ("company_id", "=", company.id), ("name", "=", label),
        ], limit=1)
        if catalog:
            return catalog
        return self.env["bc3.catalog"].create({
            "name": label, "edition": edition or False,
            "company_id": company.id,
        })

    def _archive_import(self, order, document, mode, warnings):
        """Immutable audit snapshot, including original BC3 bytes."""
        raw = self._bc3_source_bytes()
        self.env["bc3.import.history"].create({
            "name": self.filename or "BC3",
            "file_data": self.data_file,
            "checksum_sha256": hashlib.sha256(raw).hexdigest(),
            "file_size": len(raw),
            "sale_order_id": order.id if order else False,
            "catalog_id": self._active_catalog.id,
            "company_id": self._company().id,
            "user_id": self.env.user.id,
            "info_type": str(document.info_type) if document.info_type else False,
            "import_mode": mode,
            "validation_mode": self.validation_mode,
            "price_scope": self.price_scope,
            "warnings": "\n".join(warnings[:200]),
            "summary": (order.bc3_import_summary if order else "") or
                       ("%s conceptos del catálogo" % len(document.concepts)),
        })

    def _import_catalog(self, document, concepts, warnings):
        templates = self.env["product.template"]
        company = self._company()
        for concept in concepts:
            price = document.unit_price(concept, self.prefer_decomposition_price)
            templates |= self._get_or_create_product(concept, price, company, warnings)
        return templates

    def _import_budget(self, document, budget_lines, warnings, existing_templates):
        company = self._company()
        order = self._prepare_order(document)
        # Lock the target order while matching/replacing BC3 positions.
        self.env.cr.execute("SELECT id FROM sale_order WHERE id = %s FOR UPDATE", [order.id])
        current = {line.bc3_path: line for line in order.order_line if line.bc3_path}
        if len(current) != len(order.order_line.filtered(lambda line: line.bc3_path)):
            raise UserError(_("Duplicate BC3 positions on the destination order."))
        # Old versions did not store the position. Match only a unique code
        # (repeated work items need manual review to avoid a wrong mapping).
        legacy = order.order_line.filtered(lambda line: line.bc3_code and not line.bc3_path)
        item_lines = []
        sequence = 0
        Line = self.env["sale.order.line"]
        for budget_line in budget_lines:
            sequence += 10
            path = budget_key(budget_line.position)
            previous = current.get(path)
            if not previous and legacy:
                candidates = legacy.filtered(lambda line: line.bc3_code == budget_line.code)
                if len(candidates) > 1:
                    raise UserError(_("Ambiguous historical BC3 code %s: migrate positions manually.") % budget_line.code)
                if candidates:
                    previous = candidates[0]
                    legacy -= previous
            if previous and previous.bc3_code != budget_line.code:
                raise UserError(
                    _("BC3 path %s changed concept from %s to %s. Review manually.")
                    % (path, previous.bc3_code, budget_line.code)
                )
            if budget_line.kind == "chapter":
                self._create_section(order, budget_line, sequence, previous)
                continue
            concept = document.get(budget_line.code)
            product = existing_templates.filtered(
                lambda tmpl, code=budget_line.code: tmpl.bc3_code == code
            )[:1]
            if not product and concept is not None:
                product = self._get_or_create_product(
                    concept, budget_line.price, company, warnings
                )
                existing_templates |= product
            if not product:
                raise UserError(_("No product found for BC3 code %s.") % budget_line.code)
            name = self._line_name(budget_line, concept)
            uom, exact = self._uom_for(budget_line.unit)
            if not exact and budget_line.unit and not self.allow_unknown_units:
                raise UserError(
                    _("Unknown BC3 unit '%s' on %s; configure a UoM or explicitly allow a fallback.")
                    % (budget_line.unit, budget_line.code)
                )
            if not exact and budget_line.unit:
                warnings.append(_("Unit %s on %s replaced with Units.") % (budget_line.unit, budget_line.code))
                name = "%s (%s)" % (name, budget_line.unit)
            variant = product.product_variant_id or product.product_variant_ids[:1]
            if not variant:
                raise UserError(_("No product variant for %s.") % budget_line.code)
            if uom and not variant.uom_id._has_common_reference(uom):
                raise UserError(
                    _("Incompatible measurement units for %s: product %s vs BC3 %s.")
                    % (budget_line.code, variant.uom_id.display_name, uom.display_name)
                )
            vals = {
                "order_id": order.id,
                "sequence": sequence,
                "product_id": variant.id,
                "name": name,
                "product_uom_qty": budget_line.quantity,
                "price_unit": budget_line.price,
                "bc3_code": budget_line.code,
                "bc3_path": path,
                "bc3_unit": budget_line.unit or False,
                "bc3_label": budget_line.label or False,
                "bc3_factor": budget_line.factor,
                "bc3_yield": budget_line.yield_qty,
                "bc3_measured_qty": budget_line.measured_quantity if budget_line.measured_quantity is not None else 0.0,
                "bc3_is_measured": budget_line.measured_quantity is not None,
                "bc3_measurement_data": [asdict(entry) for entry in budget_line.measurement_lines],
            }
            vals.update(self._uom_vals(uom))
            vals.update(self._tax_vals(variant, order))
            if previous:
                if previous.display_type:
                    raise UserError(_("BC3 path %s previously referenced a section, not a work item.") % path)
                previous.write(vals)
                line = previous
            else:
                line = Line.create(vals)
            # Product/pricelist computations must not change BC3 source amounts.
            repair = {}
            for key in ("price_unit", "product_uom_qty", "name"):
                if line[key] != vals[key]:
                    repair[key] = vals[key]
            if repair:
                line.write(repair)
            item_lines.append(line)
        if legacy:
            raise UserError(
                _("Unmapped BC3 lines from older versions remain on the order. "
                  "Review or remove them before reimporting.")
            )
        if self.apply_coefficients:
            self._add_coefficient_lines(order, document, item_lines, sequence)
        self._write_note(order, document, item_lines)
        return order, existing_templates

    def _prepare_order(self, document):
        root = document.root_concept()
        title = ((root.summary if root else "") or document.header or document.comment or self.filename or "BC3")
        info = str(document.info_type) if document.info_type in (1, 2, 3, 4) else False
        vals = {
            "bc3_filename": self.filename or False,
            "bc3_info_type": info,
            "bc3_ci": document.ci,
            "bc3_gg": document.gg,
            "bc3_bi": document.bi,
            "bc3_baja": document.baja,
            "bc3_iva": document.iva,
            "bc3_currency": document.currency or False,
            "bc3_comment": document.comment or document.property or False,
            "bc3_catalog_id": self._active_catalog.id,
        }
        if self.sale_order_id:
            order = self.sale_order_id
            if not order.origin:
                vals["origin"] = self.filename or "BC3"
            order.write(vals)
            return order
        vals.update(
            {
                "partner_id": self.partner_id.id,
                "origin": self.filename or "BC3",
                "client_order_ref": title[:200],
            }
        )
        new_order = self.env["sale.order"].create(vals)
        if document.currency and document.currency.upper() != new_order.currency_id.name.upper():
            raise UserError(
                _("BC3 currency %s is different from quotation currency %s. "
                  "Choose a compatible pricelist; automatic conversion is not supported.")
                % (document.currency, new_order.currency_id.name)
            )
        return new_order

    def _create_section(self, order, budget_line, sequence, existing=None):
        title = budget_line.name or budget_line.code
        if budget_line.label:
            title = "%s %s" % (budget_line.label, title)
        vals = {
            "order_id": order.id,
            "sequence": sequence,
            "display_type": self._section_type(budget_line.depth),
            "name": title,
            "bc3_code": budget_line.code,
            "bc3_path": budget_key(budget_line.position),
            "bc3_label": budget_line.label or False,
            "product_uom_qty": 0.0,
        }
        if existing:
            if not existing.display_type:
                raise UserError(_("The existing BC3 section is a work item."))
            existing.write(vals)
        else:
            self.env["sale.order.line"].create(vals)

    def _section_type(self, depth):
        if depth <= 1:
            return "line_section"
        field = self.env["sale.order.line"]._fields["display_type"]
        selection = field.selection(self.env["sale.order.line"]) if callable(field.selection) else field.selection
        if any(key == "line_subsection" for key, _label in selection):
            return "line_subsection"
        return "line_section"

    def _add_coefficient_lines(self, order, document, item_lines, sequence):
        pem = sum((line.product_uom_qty or 0.0) * (line.price_unit or 0.0) for line in item_lines)
        ci_amount, baja_amount, gg_amount, bi_amount = coefficient_amounts(
            pem, document.ci, document.gg, document.bi, document.baja
        )
        rows = []
        if abs(ci_amount) > 1e-6:
            rows.append((_("Indirect costs (%s%%)") % _num(document.ci), ci_amount, "BC3-CI"))
        if abs(baja_amount) > 1e-6:
            if document.baja >= 0:
                label = _("Award discount (%s%%)") % _num(document.baja)
            else:
                label = _("Award increase (%s%%)") % _num(abs(document.baja))
            rows.append((label, -baja_amount, "BC3-BAJA"))
        if abs(gg_amount) > 1e-6:
            rows.append((_("Overheads (%s%%)") % _num(document.gg), gg_amount, "BC3-GG"))
        if abs(bi_amount) > 1e-6:
            rows.append((_("Industrial profit (%s%%)") % _num(document.bi), bi_amount, "BC3-BI"))
        previous = order.order_line.filtered(
            lambda line: line.bc3_path.startswith("coef:") if line.bc3_path else False
        )
        expected = {"coef:%s" % code.removeprefix("BC3-") for _, _, code in rows}
        invalid = previous.filtered(lambda line: line.bc3_path not in expected)
        if invalid:
            raise UserError(
                _("Some previously imported coefficient lines no longer exist in the BC3. "
                  "Delete/review those lines explicitly before importing.")
            )
        if not rows:
            if order.order_line.filtered(lambda line: line.bc3_path == "coefficients"):
                raise UserError(_("Old BC3 coefficient section must be reviewed before import."))
            return
        sequence += 10
        section = order.order_line.filtered(lambda line: line.bc3_path == "coefficients")[:1]
        section_vals = {
            "order_id": order.id,
            "sequence": sequence,
            "display_type": "line_section",
            "name": _("BC3 coefficients"),
            "bc3_path": "coefficients",
            "bc3_code": "BC3-COEF-SECTION",
            "product_uom_qty": 0.0,
        }
        section.write(section_vals) if section else self.env["sale.order.line"].create(section_vals)
        product = self._coefficient_product()
        for label, amount, code in rows:
            sequence += 10
            amount = order.currency_id.round(amount) if order.currency_id else amount
            vals = {
                "order_id": order.id,
                "sequence": sequence,
                "product_id": product.id,
                "name": label,
                "product_uom_qty": 1.0,
                "price_unit": amount,
                "bc3_code": code,
                "bc3_path": "coef:%s" % code.removeprefix("BC3-"),
            }
            vals.update(self._tax_vals(product, order))
            existing = order.order_line.filtered(lambda line: line.bc3_path == vals["bc3_path"])[:1]
            line = existing if existing else self.env["sale.order.line"].create(vals)
            if existing:
                existing.write(vals)
            if abs((line.price_unit or 0.0) - amount) > 1e-6:
                line.price_unit = amount

    def _create_certification(self, order, document, budget_lines, warnings):
        """Import a FIEBDC cumulative origin against the EXISTING contract.

        Never insert new sale lines nor alter confirmed contract quantities.
        Only the difference from already committed NET certified quantities
        becomes qty_period. A repeated posted certificate is rejected.
        """
        if "construction.certification" not in self.env:
            raise UserError(_("Install tl_construction_certification first."))
        if order.state not in ("sale", "done"):
            raise UserError(_("A certification requires a confirmed sales order."))
        # Serialize concurrent certificate imports for this contract.
        self.env.cr.execute(
            "SELECT id FROM sale_order WHERE id = %s FOR UPDATE", [order.id]
        )
        Cert = self.env["construction.certification"]
        CertLine = self.env["construction.certification.line"]
        incoming = [(line, line.measured_quantity) for line in budget_lines
                    if line.kind == "item" and line.measured_quantity is not None]
        if not incoming:
            raise UserError(_("No measured BC3 work items to certify."))
        # The order may contain contractual BC3 coefficients as additional
        # SO lines.  They have no ~M record: their certified quantity is the
        # cumulative *economic* progress ratio of the measured work items.
        contracted_items = order.order_line.filtered(
            lambda line: bool(line.bc3_path) and not line.display_type
            and not line.bc3_path.startswith("coef:")
        )
        coefficient_lines = order.order_line.filtered(
            lambda line: bool(line.bc3_path) and line.bc3_path.startswith("coef:")
            and not line.display_type
        )
        existing = contracted_items
        planned = {}
        origin_quantities = {}
        for source_line, cumulative in incoming:
            path = budget_key(source_line.position)
            target = existing.filtered(lambda line, path=path: line.bc3_path == path)
            if not target:
                # Backward compatibility for non-ambiguous rows imported before
                # BC3 paths existed. No persistent writes on confirmed orders.
                target = order.order_line.filtered(
                    lambda line, code=source_line.code: line.bc3_code == code
                    and not line.bc3_path and not line.display_type
                )
            if len(target) != 1:
                raise UserError(
                    _("BC3 measured item %s at position %s does not uniquely "
                      "match a contracted sale order line.") % (source_line.code, path)
                )
            sale_line = target[0]
            if sale_line.bc3_code != source_line.code:
                raise UserError(_("BC3 code mismatch at position %s.") % path)
            if source_line.unit and sale_line.bc3_unit and (
                _normalize_unit(source_line.unit) != _normalize_unit(sale_line.bc3_unit)
            ):
                raise UserError(
                    _("BC3 measurement unit changed for %s: %s versus contract %s. "
                      "Do not certify quantities measured in a different unit.")
                    % (source_line.code, source_line.unit, sale_line.bc3_unit)
                )
            if abs(sale_line.price_unit - source_line.price) > 0.02:
                warnings.append(
                    _("BC3 price differs from contracted price for %s "
                      "(BC3: %.4f, order: %.4f); contract price is kept.")
                    % (source_line.code, source_line.price, sale_line.price_unit)
                )
            # A type-3 BC3 is cumulative. Its ~D and ~M express the measured
            # origin, NOT the quantity of the original construction contract.
            # The contract is immutable and taken only from the confirmed SO.
            if cumulative < -1e-6:
                raise UserError(_("Negative cumulative BC3 quantity for %s.") % source_line.code)
            if sale_line.id in origin_quantities:
                raise UserError(_("Duplicate measured item %s.") % source_line.code)
            previous = CertLine.search([
                ("sale_line_id", "=", sale_line.id),
                ("certification_id.state", "in", ("approved", "invoiced")),
            ])
            credited = previous._credited_quantity() if previous else {}
            origin_net = sum(
                (line.qty_period or 0.0) - credited.get(line.id, 0.0)
                for line in previous
            )
            try:
                delta = certification_period(
                    cumulative, origin_net, sale_line.product_uom_qty,
                    tolerance=max(1e-6, 10 ** (-document.precision("DS")) / 2),
                )
            except Bc3Error as error:
                raise UserError("%s (%s): %s" % (source_line.code, path, error)) from error
            origin_quantities[sale_line.id] = cumulative
            if delta:
                planned[sale_line.id] = delta

        if coefficient_lines:
            missing = contracted_items.filtered(
                lambda line: line.id not in origin_quantities
            )
            if missing:
                raise UserError(_(
                    "A BC3 certification with contractual coefficients must "
                    "contain the cumulative measurements for all BC3 work "
                    "items. Missing: %s."
                ) % ", ".join(missing.mapped("bc3_code")[:15]))
            # Price_subtotal is the tax-excluded contractual base.  Both the
            # numerator and denominator therefore use the order's original
            # prices (including discounts and fiscal position); incoming ~C
            # prices and ~K coefficients never rewrite a confirmed contract.
            contract_base = sum(contracted_items.mapped("price_subtotal"))
            executed_base = sum(
                (line.price_reduce_taxexcl or 0.0) * origin_quantities[line.id]
                for line in contracted_items
            )
            try:
                progress = coefficient_origin_ratio(
                    executed_base, contract_base,
                    tolerance=max(1e-6, abs(contract_base) * 1e-7),
                )
            except Bc3Error as error:
                raise UserError(str(error)) from error
            for code, source_rate in (
                ("CI", document.ci), ("GG", document.gg),
                ("BI", document.bi), ("BAJA", document.baja),
            ):
                contracted_rate = getattr(order, "bc3_%s" % code.lower(), 0.0)
                if abs((contracted_rate or 0.0) - (source_rate or 0.0)) > 1e-6:
                    warnings.append(_(
                        "BC3 coefficient %s differs from the confirmed "
                        "contract (file: %s%%; contract: %s%%); contract lines are kept."
                    ) % (code, source_rate, contracted_rate))
            for coefficient in coefficient_lines:
                previous = CertLine.search([
                    ("sale_line_id", "=", coefficient.id),
                    ("certification_id.state", "in", ("approved", "invoiced")),
                ])
                credited = previous._credited_quantity() if previous else {}
                previous_net = sum(
                    (row.qty_period or 0.0) - credited.get(row.id, 0.0)
                    for row in previous
                )
                contract_qty = coefficient.product_uom_qty
                if contract_qty <= 0:
                    raise UserError(_(
                        "BC3 coefficient line %s must have a positive contracted quantity."
                    ) % coefficient.bc3_code)
                try:
                    delta = certification_period(
                        progress * contract_qty, previous_net, contract_qty,
                        tolerance=max(1e-8, 1e-7 * contract_qty),
                    )
                except Bc3Error as error:
                    raise UserError("%s: %s" % (coefficient.bc3_code, error)) from error
                if delta:
                    planned[coefficient.id] = delta
        existing_cert = Cert.search([
            ("sale_order_id", "=", order.id),
            ("certification_number", "=", document.certification_number),
        ], limit=1) if document.certification_number else Cert.browse()
        if existing_cert and existing_cert.state not in ("draft", "measured"):
            raise UserError(
                _("Certification no. %s already exists in a committed state.")
                % document.certification_number
            )
        # Avoid creating period 2 while period 1 remains in draft: uncommitted
        # quantities must be approved before another cumulative delta is read.
        other_drafts = Cert.search([
            ("sale_order_id", "=", order.id),
            ("state", "in", ("draft", "measured")),
        ]) - existing_cert
        if other_drafts:
            raise UserError(
                _("Approve or cancel the other draft certifications of this "
                  "contract before importing a new BC3 certificate.")
            )
        # Even a zero-delta reimport must replace the contents of the draft.
        # Returning early here left stale lines that could later be approved.
        if not planned and not existing_cert:
            warnings.append(_("The BC3 certificate adds no quantity above the committed net origin."))
            return
        vals = {
            "sale_order_id": order.id,
            "date": document.certification_date or fields.Date.context_today(self),
        }
        if document.certification_number:
            vals["certification_number"] = document.certification_number
        certification = existing_cert or Cert.create(vals)
        if existing_cert:
            existing_cert.write({"date": vals["date"], "state": "draft"})
            # Changing a draft imported certificate cannot create duplicated
            # lines; only update/delete within the uncommitted document.
            existing_cert.line_ids.unlink()
        if not planned:
            warnings.append(_(
                "BC3 origin equals the already committed origin: existing draft "
                "certification has been emptied and cannot approve obsolete quantities."
            ))
            return
        for sale_line_id, qty_period in planned.items():
            CertLine.create({
                "certification_id": certification.id,
                "sale_line_id": sale_line_id,
                "qty_period": qty_period,
            })

    def _get_or_create_product(self, concept, price, company, warnings):
        """Never silently alter an ordinary product with a matching SKU."""
        Template = self.env["product.template"]
        domain = [
            ("bc3_code", "=", concept.code),
            ("bc3_catalog_id", "=", self._active_catalog.id),
        ]
        if "company_id" in Template._fields and company:
            domain += ["|", ("company_id", "=", False), ("company_id", "=", company.id)]
        candidates = Template.search(domain, limit=2)
        if len(candidates) > 1:
            raise UserError(
                _("Multiple products have BC3 code %s; resolve the ambiguity first.")
                % concept.code
            )
        template = candidates[:1]
        uom, exact = self._uom_for(concept.unit)
        if not exact and concept.unit and not self.allow_unknown_units:
            raise UserError(_("BC3 concept %s has unknown unit %s.") % (concept.code, concept.unit))
        foreign_price = bool(
            getattr(self, "_source_currency", False)
            and self._source_currency.upper() != company.currency_id.name.upper()
        )
        vals = {
            "bc3_catalog_id": self._active_catalog.id,
            "bc3_code": concept.code,
            "bc3_unit": concept.unit or False,
            "bc3_text": concept.text or False,
            "bc3_concept_type": concept.concept_type or False,
            "name": concept.summary or concept.code,
        }
        if foreign_price:
            # list_price is denominated in the company's currency, whereas
            # the source BC3 price belongs to the quotation's foreign currency.
            # Keep the foreign amount only on the sale line, not on the product.
            warnings.append(
                _("Foreign-currency price of BC3 concept %s was NOT stored "
                  "as the product's company-currency sales price.") % concept.code
            )
            vals["list_price"] = 0.0
        else:
            vals["list_price"] = price
        if concept.text:
            vals["description_sale"] = concept.text
        if template:
            if self.update_existing:
                # An existing product's company-currency list price must never
                # be reset by a quotation in a different currency.
                if foreign_price:
                    vals.pop("list_price", None)
                template.with_company(company).write(vals)
            return template
        if "company_id" in Template._fields:
            # The catalog is company-specific. Its products must not be shared
            # (company_id=False), or check_company=True would reject this link.
            vals["company_id"] = company.id
        vals.update({
            "default_code": "BC3-%s" % concept.code,
            "sale_ok": True,
            "purchase_ok": concept.concept_type in ("3", "4"),
        })
        product_type = "consu" if concept.concept_type in ("3", "4") else "service"
        if "type" in Template._fields:
            vals["type"] = product_type
        if uom:
            vals["uom_id"] = uom.id
            if "uom_po_id" in Template._fields:
                vals["uom_po_id"] = uom.id
        return Template.with_company(company).create(vals)

    def _coefficient_product(self):
        template = self.env["product.template"].search([
            ("bc3_code", "=", "BC3-COEF"),
            ("bc3_catalog_id", "=", self._active_catalog.id),
        ], limit=1)
        if template:
            return template.product_variant_id
        vals = {
            "name": _("BC3 coefficient"),
            "default_code": "BC3-COEF",
            "bc3_code": "BC3-COEF",
            "bc3_catalog_id": self._active_catalog.id,
            "sale_ok": True,
            "purchase_ok": False,
            "list_price": 0.0,
        }
        Template = self.env["product.template"]
        if "company_id" in Template._fields:
            vals["company_id"] = self._company().id
        if "type" in Template._fields:
            vals["type"] = "service"
        elif "detailed_type" in Template._fields:
            vals["detailed_type"] = "service"
        return Template.create(vals).product_variant_id

    def _company(self):
        if self.sale_order_id:
            return self.sale_order_id.company_id
        return self.env.company

    def _uom_for(self, unit):
        key = _normalize_unit(unit)
        if not key:
            return self.env.ref("uom.product_uom_unit", raise_if_not_found=False), True
        cache = getattr(self, "_uom_cache", None)
        if cache is None:
            cache = {}
            self._uom_cache = cache
        if key in cache:
            return cache[key]
        uom = self.env["uom.uom"]
        xmlid = _UOM_XMLID.get(key)
        if xmlid:
            uom = self.env.ref(xmlid, raise_if_not_found=False) or uom
        exact = bool(uom)
        if not uom:
            for name in _UOM_NAMES.get(key, [key]):
                found = self.env["uom.uom"].search([("name", "=", name)], limit=1)
                if found:
                    uom = found
                    exact = True
                    break
        if not uom:
            uom = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
            exact = False
        # Odoo 20 archives several standard construction units (m3, cm, km).
        # Do not silently use an inactive UoM or replace m3 with Units.
        if uom and not uom.active:
            raise UserError(
                _("BC3 unit %s is archived in Odoo (%s). Activate it in Units of "
                  "Measure before importing; no conversion to Units is performed.")
                % (unit, uom.display_name)
            )
        cache[key] = (uom, exact)
        return uom, exact

    def _uom_vals(self, uom):
        if not uom:
            return {}
        Line = self.env["sale.order.line"]
        for name in ("product_uom_id", "product_uom"):
            field = Line._fields.get(name)
            if field and field.type == "many2one" and not field.related:
                return {name: uom.id}
        return {}

    def _tax_vals(self, product, order):
        """Apply the actual SO fiscal position, not raw product VAT."""
        product = product.with_company(order.company_id)
        taxes = product.taxes_id if "taxes_id" in product._fields else self.env["account.tax"]
        taxes = taxes.filtered(lambda tax: not tax.company_id or tax.company_id == order.company_id)
        if order.fiscal_position_id:
            taxes = order.fiscal_position_id.map_tax(taxes)
        return {"tax_ids": [(6, 0, taxes.ids)]}

    def _line_name(self, budget_line, concept):
        title = budget_line.name or budget_line.code
        if budget_line.label:
            title = "%s %s" % (budget_line.label, title)
        text = (budget_line.text or "").strip()
        if text and text != (budget_line.name or "").strip():
            title = "%s\n%s" % (title, text)
        return title

    def _write_note(self, order, document, item_lines):
        pem = sum((line.product_uom_qty or 0.0) * (line.price_unit or 0.0) for line in item_lines)
        if order.currency_id:
            pem = order.currency_id.round(pem)
        info = dict(order._fields["bc3_info_type"].selection).get(order.bc3_info_type, _("Unspecified"))
        lines = [
            _("BC3 file: %s") % (self.filename or "-"),
            _("Information: %s") % info,
            _("Material budget (PEM): %s") % pem,
            _("CI %s%% | Overheads %s%% | Industrial profit %s%% | Discount %s%% | VAT %s%%")
            % (
                _num(document.ci),
                _num(document.gg),
                _num(document.bi),
                _num(document.baja),
                _num(document.iva),
            ),
        ]
        if document.currency and order.currency_id and document.currency != (order.currency_id.name or ""):
            lines.append(
                _("BC3 currency is %s and the order currency is %s.")
                % (document.currency, order.currency_id.name)
            )
        if self.apply_coefficients:
            lines.append(_("Coefficients were added as extra lines. VAT was not."))
        else:
            lines.append(
                _("Coefficients were stored and not applied, so a price that already includes them is not counted twice.")
            )
        note_lines = "\n".join(lines)
        # Keep standard quotation T&Cs unchanged and avoid appending duplicated
        # BC3 information on each reimport.
        order.bc3_import_summary = note_lines

    def _post_log(self, order, templates, document, mode, warnings):
        summary = _(
            "BC3 import (%(mode)s): %(products)s products, %(lines)s order lines."
        ) % {
            "mode": mode,
            "products": len(templates),
            "lines": len(order.order_line) if order else 0,
        }
        if warnings:
            summary = "%s\n%s" % (summary, "\n".join(warnings[:40]))
        if order:
            order.message_post(body="<br/>".join(html.escape(line) for line in summary.split("\n")))
        elif warnings:
            _logger.info("BC3 catalog warnings: %s", summary)

    def _open_result(self, order, templates):
        if order:
            return {
                "type": "ir.actions.act_window",
                "name": _("Budget"),
                "res_model": "sale.order",
                "view_mode": "form",
                "res_id": order.id,
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("BC3 products"),
            "res_model": "product.template",
            "view_mode": "list,form",
            "domain": [("id", "in", templates.ids)],
        }


def _normalize_unit(unit):
    text = (unit or "").strip().lower().replace(" ", "").replace(".", "")
    text = text.replace("²", "2").replace("³", "3")
    return _UNIT_ALIAS.get(text, text)


def _num(value):
    return ("%.4f" % (value or 0.0)).rstrip("0").rstrip(".")
