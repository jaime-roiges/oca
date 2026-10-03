# Copyright 2020 Trey, Kilobytes de Soluciones
# Copyright 2020 Tecnativa - Pedro M. Baeza
# Copyright 2026 OpenAI - Odoo 20 migration
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    price_method = fields.Selection(
        selection=[
            ("carrier", "Carrier obtained price"),
            ("fixed", "Fixed price"),
            ("base_on_rule", "Based on Rules"),
        ],
        default="carrier",
        string="Price method",
    )

    def _use_forced_price_method(self, order):
        """Return whether local fixed/rule pricing must replace the carrier quote.

        Keep the 19.0 free-over behavior: once the free-shipping threshold is met,
        use the real carrier quote so ``carrier_price`` can still reflect the provider
        cost while the core zeroes the customer-facing price.
        """
        self.ensure_one()
        return self.price_method in ("fixed", "base_on_rule") and (
            not self.free_over
            or not self.amount
            or self._compute_currency(
                order, order.amount_total, "pricelist_to_company"
            )
            < self.amount
        )

    def _apply_price_method_margins(self, price, order):
        """Apply core delivery margins using ``price_method`` as pricing provider.

        Odoo core deliberately skips margins for the ``fixed`` provider. The 19.0
        addon achieved this by temporarily writing ``delivery_type``. Odoo 20 has
        side effects on that write, so reproduce the pricing semantics without
        mutating the carrier configuration.
        """
        self.ensure_one()
        if self.price_method == "fixed":
            return float(price)
        fixed_margin = self._compute_currency(
            order, self.fixed_margin, "company_to_pricelist"
        )
        return float(price) * (1.0 + self.margin) + fixed_margin

    def _rate_shipment_with_price_method(self, order):
        """Run the Odoo 20 rate pipeline with ``price_method`` as dispatcher."""
        self.ensure_one()
        method = self.price_method
        res = getattr(self, f"{method}_rate_shipment")(order)

        company = self.company_id or order.company_id or self.env.company
        res["price"] = self.product_id._get_tax_included_unit_price(
            company,
            company.currency_id,
            order.date_order,
            "sale",
            fiscal_position=order.fiscal_position_id,
            product_price_unit=res["price"],
            product_currency=company.currency_id,
        )
        res["price"] = order.currency_id.round(
            self._apply_price_method_margins(res["price"], order)
        )
        res["carrier_price"] = res["price"]

        amount_without_delivery = order._compute_amount_total_without_delivery()
        if (
            res["success"]
            and self.free_over
            and method != "base_on_rule"
            and self._compute_currency(
                order, amount_without_delivery, "pricelist_to_company"
            )
            >= self.amount
        ):
            res["warning_message"] = self.env._(
                "The shipping is free since the order amount exceeds %.2f.",
                self.amount,
            )
            res["price"] = 0.0
        return res

    def rate_shipment(self, order):
        if self._use_forced_price_method(order):
            return self._rate_shipment_with_price_method(order)
        return super().rate_shipment(order)

    def send_shipping(self, pickings):
        res = super().send_shipping(pickings)
        if self.price_method in ("fixed", "base_on_rule"):
            rates = getattr(self, f"{self.price_method}_send_shipping")(pickings)
            for index, rate in enumerate(rates):
                rate = dict(rate)
                rate.pop("tracking_number", None)
                res[index].update(rate)
        return res

    def _get_price_from_picking(self, total, weight, volume, quantity, wv=0.0):
        if (
            self.price_method == "base_on_rule"
            and self.free_over
            and total >= self.amount
        ):
            return 0.0
        return super()._get_price_from_picking(total, weight, volume, quantity, wv)
