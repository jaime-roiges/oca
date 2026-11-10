# Odoo 20 port notes (QA v13.4)

This is a non-official Odoo 20 port of the OCA module. The official source is
preserved in the uploaded archive, and the port changes are limited to 20.0
compatibility. Do not present this version as an official merged OCA release.

- Odoo 20 unified security syntax: operation `crw` -> `cru`.
- Odoo 20 no longer defines `web.external_layout_boxed`,
  `web.external_layout_striped` or `web.external_layout_bold`. Those are now
  report table styles selected via `report_tables_id`.
- Report article is rendered by `web.external_layout_body`. Brand CSS is
  attached to that common template and the header/footer of the remaining
  Odoo 20 layouts.
- `web.external_layout` is extended at its Odoo 20 dispatch node, preserving
  the brand override and the native company fallback.
- `report_tables_id` is added to `res.brand` and the layout wizard so that
  reports rendered with the brand as `company` have this required field.
- The SCSS asset path from the supplied module has not been changed; its
  rendering and PDF output must be checked in Odoo 20.

No Odoo server installation, runtime QWeb rendering or PDF generation was
executed in this workspace. Test in a staging database first.
