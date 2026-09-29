This module enriches Odoo 20 bank accounts from an IBAN using the `schwifty`
IBAN registry.

Odoo 20 no longer uses a separate `res.bank` master record. Bank information is
stored directly on `res.partner.bank`, so this module fills the bank name, BIC,
country and bank/institution code directly on the bank account.
