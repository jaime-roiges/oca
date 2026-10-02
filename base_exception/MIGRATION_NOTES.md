# Odoo 20 migration notes

- Updated module version to `20.0.1.0.1`.
- Converted the four ACL rows from `ir.model.access` into `ir.access` using Odoo 20's `operation` letters. Internal users retain read access; the exception manager group retains create, read, write, and unlink.
- The security XML only defines the `base_exception.group_exception_rule_manager` group; this addon contains no `ir.rule` records to convert.
- The `ir.access.csv` is loaded after the module's views, following the Odoo 20 data-loading convention.
