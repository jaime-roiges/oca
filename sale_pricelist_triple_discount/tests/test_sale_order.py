# Copyright 2023 Simone Rubino - Aion Tech
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSalePrices(SaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("product.group_product_pricelist")
        cls.env.user.group_ids |= cls.env.ref("sale.group_discount_per_so_line")

    def _add_rule(self, **values):
        pricelist_form = Form(self.pricelist)
        with pricelist_form.item_ids.new() as item:
            item.compute_price = values.pop("compute_price", "discount")
            for field, value in values.items():
                setattr(item, field, value)
        pricelist = pricelist_form.save()
        return pricelist.item_ids[0]

    def _new_order_line(self):
        order_form = Form(self.empty_order)
        with order_form.order_line.new() as line:
            line.product_id = self.product
        return order_form.save().order_line

    def test_plain_discount_is_exposed_as_three_discounts(self):
        rule = self._add_rule(price_discount=10, discount2=20, discount3=30)
        line = self._new_order_line()

        self.assertTrue(rule.is_plain_discount)
        self.assertAlmostEqual(rule._get_triple_discount(), 49.6)
        self.assertEqual(line.discount1, 10)
        self.assertEqual(line.discount2, 20)
        self.assertEqual(line.discount3, 30)
        self.assertEqual(line.price_unit, self.product.list_price)
        self.assertAlmostEqual(line.price_subtotal, self.product.list_price * 0.504)

    def test_complex_discount_is_baked_into_price(self):
        rule = self._add_rule(
            price_discount=10,
            discount2=20,
            discount3=30,
            price_surcharge=1,
        )
        line = self._new_order_line()

        self.assertFalse(rule.is_plain_discount)
        self.assertFalse(line.discount1)
        self.assertFalse(line.discount2)
        self.assertFalse(line.discount3)
        self.assertAlmostEqual(
            line.price_unit,
            self.product.list_price * 0.504 + 1,
        )

    def test_markup_keeps_extra_discounts_in_price(self):
        rule = self._add_rule(
            compute_price="markup",
            price_markup=10,
            discount2=20,
            discount3=30,
        )
        line = self._new_order_line()

        self.assertFalse(rule.is_plain_discount)
        self.assertFalse(line.discount1)
        self.assertFalse(line.discount2)
        self.assertFalse(line.discount3)
        # +10%, then -20%, then -30% => factor 0.616
        self.assertAlmostEqual(line.price_unit, self.product.list_price * 0.616)

    def test_pricelist_rule_write_does_not_search_nonstored_rule_field(self):
        """Editing a pricelist rule must not SQL-search SOL.pricelist_item_id."""
        rule = self._add_rule(
            compute_price="markup",
            price_markup=10,
            discount2=20,
            discount3=30,
        )
        rule.write({"price_markup": 12})
        self.assertEqual(rule.price_markup, 12)

    def test_recompute_prices_refreshes_three_discounts(self):
        rule = self._add_rule(price_discount=10, discount2=20, discount3=30)
        line = self._new_order_line()
        self.assertEqual((line.discount1, line.discount2, line.discount3), (10, 20, 30))

        rule.write({"discount2": 5, "discount3": 0})
        line.order_id._recompute_prices()
        self.assertEqual((line.discount1, line.discount2, line.discount3), (10, 5, 0))

    def test_pricelist_readonly(self):
        rule = self._add_rule(price_discount=10, discount2=20, discount3=30)
        readonly_pricelist = rule.pricelist_id.with_user(self.sale_user)
        self.assertTrue(readonly_pricelist.has_access("read"))
        self.assertFalse(readonly_pricelist.has_access("write"))
        readonly_pricelist.read()
        readonly_pricelist.item_ids.read()
