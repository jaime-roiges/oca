# account_financial_risk 19.0 → 20.0

- Rama OCA/credit-control 19.0.
- Mecánico: version, ACL, reglas, report_file, t-esc→t-out.
- Sin rediseño.

## 20.0.1.0.1

- Fix Odoo 20 portal QWeb call semantics for `financial_risk_info`: pass `partner` as a `t-call` parameter instead of setting it in the call body.
- Fix the credit limit monetary widget to use `commercial_partner.risk_currency_id` explicitly, avoiding an undefined `risk_currency_id` variable in the portal context.
