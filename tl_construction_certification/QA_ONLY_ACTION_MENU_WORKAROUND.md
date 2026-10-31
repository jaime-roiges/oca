# QA-only Action menu workaround – tl_construction_certification 20.0.1.57.0

This is a **diagnostic build for isolated Odoo 20 QA only**, based on 20.0.1.56.0.
It does NOT fix the manual-field setup ordering issue in imported Industry addons.

During QA module install/update, sale.view_order_form is inherited by
`views/sale_order_views.xml`, which causes view validation to fail with
`x_total_discount_amount` missing, although the field exists in a normal registry.
To continue isolated functional tests, this build deliberately does NOT load
the sale.order inherited view from the manifest. The original XML remains
in the ZIP for reference and later restoration.

Instead, a context menu action is bound to the sale.order form via
`views/sale_order_context_actions.xml`.

Feature differences:
- No original sale.order header buttons or smart buttons.
- In the BC3 build, no BC3 notebook tab or BC3 columns in the sale order form.
- Use the sale order **Action** menu (or the existing module menus) for access.
- Data models, business methods, taxes, accounting, and tests remain unchanged.

This build must NOT be deployed to production as a final fix; the full user
interface still requires an upstream Odoo/Industry resolution.
Do not run `-u all` on production to investigate.
