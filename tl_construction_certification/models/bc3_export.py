# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from pathlib import Path
from hashlib import sha256

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryValue, BinaryBytes
from odoo.addons.tl_construction_bc3.lib.bc3_parser import Bc3Error, parse_bc3
from odoo.addons.tl_construction_bc3.lib.bc3_certification_export import export_certification, budget_from_order


class ConstructionCertification(models.Model):
    _inherit = "construction.certification"

    def action_export_bc3(self):
        self.ensure_one()
        self.check_access('read')
        if self.state not in ('approved', 'invoiced') or self.is_retention_liquidation:
            raise UserError(_("Only an approved work certification can be exported to BC3."))
        later = self.search_count([
            ('sale_order_id', '=', self.sale_order_id.id),
            ('state', 'in', ['approved', 'invoiced']),
            '|', ('date', '>', self.date), '&', ('date', '=', self.date), ('id', '>', self.id),
        ])
        if later:
            raise UserError(_("Only the latest committed certification can be exported; later certifications already exist."))
        history = self.sale_order_id.bc3_import_ids.filtered(
            lambda item: item.info_type == '2' and item.create_date <= self.create_date
        ).sorted(key=lambda item: (item.create_date, item.id), reverse=True)[:1]
        try:
            sale_lines = self.sale_order_id.order_line.filtered(
                lambda line: not line.display_type and not (line.bc3_path or '').startswith('coef:')
            )
            if history:
                data = history.with_context(bin_size=False).file_data
                if not isinstance(data, BinaryValue):
                    raise UserError(_("The archived BC3 cannot be read as original bytes."))
                raw = data.content
                if sha256(raw).hexdigest() != history.checksum_sha256:
                    raise UserError(_("The archived BC3 checksum does not match; export stopped."))
                scope = history.price_scope or 1
                filename = Path(history.name).stem
                by_position = {line.bc3_path: line for line in sale_lines if line.bc3_path}
            else:
                if self.sale_order_id.bc3_filename or sale_lines.filtered('bc3_path'):
                    raise UserError(_("The original BC3 budget is not archived for this order."))
                records = []
                for sale_line in self.sale_order_id.order_line.sorted(key=lambda item: (item.sequence, item.id)):
                    if sale_line.display_type in ('line_section', 'line_subsection'):
                        records.append({'id': sale_line.id, 'kind': sale_line.display_type, 'name': sale_line.name})
                    elif not sale_line.display_type:
                        records.append({
                            'id': sale_line.id, 'kind': 'item', 'name': sale_line.name,
                            'quantity': sale_line.product_uom_qty, 'price': sale_line.price_reduce_taxexcl,
                            'unit': sale_line.product_uom_id.name,
                        })
                raw, position_ids = budget_from_order(records, self.currency_id.name)
                by_position = {pos: sale_lines.filtered(lambda line: line.id == line_id) for pos, line_id in position_ids.items()}
                scope = 1
                filename = self.sale_order_id.name.replace('/', '-')
            document = parse_bc3(raw, strict=True, price_scope=scope)
            source_lines = [line for line in document.iter_budget_lines() if line.kind == 'item']
            source_paths = {'.'.join(item.position) for item in source_lines}
            if set(by_position) != source_paths or len(sale_lines) != len(source_paths):
                raise UserError(_("The order no longer matches the BC3 budget positions; export stopped."))
            if document.currency and document.currency != self.currency_id.name:
                raise UserError(_("The original BC3 currency differs from the order currency."))
            previous = self._get_previous_certifications(self._committed_states)
            previous_lines = previous.mapped('line_ids').sorted(
                key=lambda line: (line.certification_id.date, line.certification_id.id, line.id)
            )
            previous_map = {line.sale_line_id.id: line for line in previous_lines}
            current_map = {line.sale_line_id.id: line for line in self.line_ids}
            cumulative = {}
            for item in source_lines:
                path = '.'.join(item.position)
                target = by_position[path]
                if len(target) != 1 or (history and target.bc3_code != item.code):
                    raise UserError(_("The code at BC3 position %(position)s no longer matches the order.", position=path))
                if abs(target.product_uom_qty - item.quantity) > 1e-6 or abs(target.price_reduce_taxexcl - item.price) > 1e-6:
                    raise UserError(_("The contract quantity or price changed at BC3 position %(position)s; review before export.", position=path))
                line = current_map.get(target.id) or previous_map.get(target.id)
                if line and abs(line.price_unit - target.price_reduce_taxexcl) > 1e-6:
                    raise UserError(_("The certified price differs from the current contract at BC3 position %(position)s.", position=path))
                if line and abs(line.qty_origin - line.qty_origin_net) > 1e-7:
                    raise UserError(_("Posted credit notes affect position %(position)s; review the cumulative measurement before export.", position=path))
                cumulative[path] = line.qty_origin if line else 0.0
            output = export_certification(raw, cumulative, self.certification_number, self.date, scope)
        except Bc3Error as error:
            raise UserError(_("BC3 export failed: %(reason)s", reason=str(error))) from error
        name = '%s#certificacion%03d.bc3' % (filename, self.certification_number)
        attachment = self.env['ir.attachment'].create({
            'name': name, 'type': 'binary', 'datas': BinaryBytes(output),
            'mimetype': 'application/octet-stream',
            'res_model': self._name, 'res_id': self.id,
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % attachment.id, 'target': 'self'}
