# Dimpal B2B credit checkout and blanket agreements (Odoo 20)

This addon is deliberately a **thin integration**. Requires:

- `website_sale_checkout_skip_payment` from the OCA 20.0 migration PR #1371 (not redistributed here).
- `website_sale_manufactured_for_partner` and its data model addon.
- `tl_dimpal_portal_blanket`, `sale_order_blanket_order`, `tl_dimpal_blanket_management`.

## Normal orders

For a **registered B2B customer with commercial company** whose `skip_website_checkout_payment` is enabled, the OCA module confirms checkout without online payment. The checkbox is an administrative credit authorization, NOT a credit-risk scoring algorithm or a guarantee of positive credit availability. Configure payment terms, follow-up and credit limits separately. All unflagged B2C/other accounts retain the standard payment provider checkout.

The Dimpal bridge verifies that the logged-in user's commercial partner matches the cart's ordering company and website, and that exclusive products belong to that account. The payment bypass is not granted by selecting a billing or shipping address.

## Contracted items

A product with an active blanket order and positive amount to call-off cannot be sold through a **new ordinary shop order**. The shop cannot automatically create zero-priced call-offs and charge a second time. The customer requests partial releases through `/my/dimpal/contracts`, which are approved using the OCA call-off wizard. For ordinary shop orders, automatic OCA call-off splitting is disabled.

## Limits and QA requirements

- OCA PR #1371 is open: inspect and test it before running the bridge.
- `sale_financial_risk` or another credit-limit control needs its own module/configuration and acceptance tests; this addon does not compute risk.
- One product in multiple concurrent contracts is restricted for regular checkout if any eligible contract has remaining units, and the portal must select the correct contract.
- No Odoo server has been run here; check views, URLs, XML IDs and method chains on Odoo 20 Community + Enterprise in QA.
- This is not record-level confidentiality: review image/document download, website caches, custom integrations, product feeds and alternative snippets before exposing sensitive pricing/catalogs.
