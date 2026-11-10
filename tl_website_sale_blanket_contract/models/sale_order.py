# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from .packaging import _tl_whole_package_quantity


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _tl_check_contract_packaging(self, product, uom, quantity):
        """Server-side invariant for cart, quantity updates and confirmation."""
        if (
            product.tl_contract_whole_pack_only
            and uom != product.uom_id
            and not _tl_whole_package_quantity(quantity)
        ):
            raise UserError(_(
                "This contract requires complete packages of %(packaging)s. "
                "Enter a positive whole number of packages.",
                packaging=uom.name,
            ))

    def _tl_web_partner(self):
        """Always resolve to the actual logged-in user, not sudo order owner."""
        self.ensure_one()
        try:
            user = request.env.user
            if user._is_public():
                return self.env["res.partner"]
            if (user.partner_id.commercial_partner_id !=
                    self.partner_id.commercial_partner_id):
                raise AccessError(_("The cart does not belong to this customer."))
            return user.partner_id
        except RuntimeError:
            return self.partner_id

    def _tl_select_web_blanket(self, product, qty, uom, *, explicit_id=None, existing=None):
        self.ensure_one()
        partner = self._tl_web_partner()
        if not partner:
            return self.env["sale.blanket.order.line"]
        lines = self.env["sale.blanket.order.line"]._tl_website_candidates(
            product, partner, self.company_id, self.currency_id
        )
        if not lines:
            if explicit_id:
                raise AccessError(_("The selected contract is not available for this customer."))
            return lines
        if explicit_id:
            try:
                selected_id = int(explicit_id)
            except (TypeError, ValueError):
                raise AccessError(_("Invalid contract selection.")) from None
            lines = lines.filtered(lambda line: line.id == selected_id)
            if not lines:
                raise AccessError(_("The selected contract is not available for this customer."))
        elif existing and existing.blanket_order_line in lines:
            lines = existing.blanket_order_line
        elif len(lines) != 1:
            raise UserError(_(
                "Several active contracts exist for this product. "
                "Select the contract explicitly from My Contracts."
            ))
        line = lines[0]
        if not line._tl_available_for_sale_line(qty, uom, existing):
            raise UserError(_("The requested quantity exceeds the available contract balance."))
        return line

    def _cart_find_product_line(self, product_id, uom_id, **kwargs):
        lines = super()._cart_find_product_line(product_id, uom_id=uom_id, **kwargs)
        explicit_id = kwargs.get("tl_blanket_line_id")
        if self.website_id and explicit_id:
            try:
                line_id = int(explicit_id)
            except (TypeError, ValueError):
                return lines.browse()
            return lines.filtered(lambda rec: rec.blanket_order_line.id == line_id)
        return lines

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        if not self.website_id or quantity <= 0:
            return super()._cart_add(product_id, quantity=quantity, uom_id=uom_id, **kwargs)
        self.ensure_one()
        product = self.env["product.product"].browse(int(product_id)).exists()
        if product:
            product = product.with_context(website_id=self.website_id.id)
        if not product:
            raise UserError(_("The requested product no longer exists."))
        if not uom_id or not product._has_multiple_uoms():
            uom = product._get_main_uom()
        else:
            uom = self.env["uom.uom"].browse(int(uom_id)).exists()
        if (
            not uom
            or uom not in product._get_available_uoms()
            or uom in self.website_id.restricted_uom_ids
        ):
            raise UserError(_("Invalid unit of measure for the selected product."))
        explicit_id = kwargs.pop("tl_blanket_line_id", None)
        current = self.order_line.filtered(
            lambda l: l.product_id == product and l.product_uom_id == uom and
            not l.display_type and not l.linked_line_id
        )
        existing = current.filtered(
            lambda l: l.blanket_order_line.id == int(explicit_id)
        )[:1] if explicit_id and str(explicit_id).isdigit() else current[:1]
        requested_total = quantity + (existing.product_uom_qty if existing else 0.0)
        contract = self._tl_select_web_blanket(
            product, requested_total, uom, explicit_id=explicit_id, existing=existing,
        )
        if current and not contract:
            # Never silently turn an already contracted line into a normal sale.
            if current.filtered("blanket_order_line"):
                raise UserError(_("Refresh your cart: its contract is no longer available."))
        new_kwargs = dict(kwargs)
        if contract:
            self._tl_check_contract_packaging(product, uom, requested_total)
            new_kwargs["tl_blanket_line_id"] = contract.id
        result = super()._cart_add(product_id, quantity=quantity, uom_id=uom.id, **new_kwargs)
        order_line = self.order_line.filtered(lambda rec: rec.id == result.get("line_id"))
        if contract and order_line:
            order_line.write({
                "blanket_order_line": contract.id,
                "price_unit": contract._tl_price_for_uom(order_line.product_uom_id),
                "technical_price_unit": contract._tl_price_for_uom(order_line.product_uom_id),
            })
        return result

    def _cart_update_line_quantity(self, line_id, quantity, **kwargs):
        if self.website_id and quantity > 0:
            line = self.order_line.filtered(lambda r: r.id == line_id)
            if line:
                contract = self._tl_select_web_blanket(
                    line.product_id, quantity, line.product_uom_id,
                    explicit_id=line.blanket_order_line.id or kwargs.get("tl_blanket_line_id"),
                    existing=line,
                )
                if line.blanket_order_line and not contract:
                    raise UserError(_("The contract on this cart line has expired."))
                if contract:
                    if line.product_uom_id in self.website_id.restricted_uom_ids:
                        raise UserError(_("Invalid unit of measure for the selected product."))
                    self._tl_check_contract_packaging(
                        line.product_id, line.product_uom_id, quantity,
                    )
        result = super()._cart_update_line_quantity(line_id, quantity, **kwargs)
        if self.website_id and quantity > 0:
            line = self.order_line.filtered(lambda r: r.id == line_id)
            if line and line.blanket_order_line:
                price = line.blanket_order_line._tl_price_for_uom(line.product_uom_id)
                line.write({"price_unit": price, "technical_price_unit": price})
        return result

    def action_confirm(self):
        website_orders = self.filtered("website_id")
        for order in website_orders:
            order._tl_web_partner()
            agreement_lines = order.order_line.mapped("blanket_order_line")
            if agreement_lines:
                # Serialize contractual consumption across concurrent checkouts.
                self.env.cr.execute(
                    "SELECT id FROM sale_blanket_order_line WHERE id IN %s ORDER BY id FOR UPDATE",
                    [tuple(sorted(agreement_lines.ids))],
                )
                self.env.flush_all()
                agreement_lines.invalidate_recordset(["remaining_uom_qty", "sale_lines"])
            for sale_line in order.order_line.filtered(lambda l: l.product_id and not l.display_type):
                agreement = sale_line.blanket_order_line
                if agreement:
                    order._tl_select_web_blanket(
                        sale_line.product_id, sale_line.product_uom_qty,
                        sale_line.product_uom_id, explicit_id=agreement.id,
                        existing=sale_line,
                    )
                    if sale_line.product_uom_id in order.website_id.restricted_uom_ids:
                        raise UserError(_("Invalid unit of measure for the selected product."))
                    order._tl_check_contract_packaging(
                        sale_line.product_id, sale_line.product_uom_id,
                        sale_line.product_uom_qty,
                    )
                    price = agreement._tl_price_for_uom(sale_line.product_uom_id)
                    if order.currency_id.compare_amounts(sale_line.price_unit, price):
                        sale_line.write({"price_unit": price, "technical_price_unit": price})
                else:
                    # A cart must not evade the contract simply by unsetting its line.
                    partner = order._tl_web_partner()
                    if partner and self.env["sale.blanket.order.line"]._tl_website_candidates(
                        sale_line.product_id, partner, order.company_id, order.currency_id
                    ):
                        raise UserError(_("A contractual product must use its active contract."))
        return super().action_confirm()
