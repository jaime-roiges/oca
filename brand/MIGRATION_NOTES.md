# Odoo 20 migration

- Version bumped to 20.0.1.0.0.
- Security converted to `ir.access.csv`.
- The former group-less read ACL is represented by read permissions for internal, portal and public users; the multi-company rule remains a group-less restriction.
- `ir.access.csv` is loaded after views, following Odoo 20 core ordering.
