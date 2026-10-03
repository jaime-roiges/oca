# account_financial_report 19.0 → 20.0

- Version 20.0.0.0.23. Fuente OCA/account-financial-reporting 19.0.
- ir.access.csv + regla multi-compañía.
- report_file eliminado de ir.actions.report.
- XPath account.view_account_form field active y block#analytic en ajustes: OK 20.0.
- Depende de account, date_range y report_xlsx (estos dos ya migrados antes).
- OWL/JS sin reescritura.
- Sin rediseño.
- Odoo 20 elimina `account.group`; la jerarquía del plan contable vive ahora en
  `account.account.parent_id` / `parent_ids` y expone `code_path` / `name_path`.
  Se eliminó la extensión `models/account_group.py` y el balance de sumas y saldos
  usa la jerarquía nativa de `account.account`.
- Los enlaces QWeb de filas jerárquicas abren ahora `account.account`.
- `security/ir.access.csv` se carga al final de `data`, siguiendo el orden de Odoo 20.
- Frontend OWL 3: `useEffect` se sustituye por `useLayoutEffect` desde
  `@web/owl2/utils`, según la capa de compatibilidad de Odoo 20.
- `ReportAction` de Odoo 20 ya no expone `report_file`; la acción XLSX se construye
  únicamente con `report_name`.

## 2026-10-03 - Odoo 20 ReportAction iframe lifecycle

- Fixed the Odoo 20 frontend crash `Cannot read properties of undefined (reading 'el')`.
- Odoo 20 `web.ReportAction` no longer exposes an iframe `useRef` (`this.iframe`).
- The AFR patch now extends `onIframeLoaded(ev)` and enriches `ev.currentTarget` after the core handler runs.
- Removed the obsolete OWL hook/ref based integration from `static/src/js/report.esm.js`.
