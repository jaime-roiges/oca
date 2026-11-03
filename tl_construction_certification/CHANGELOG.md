## 20.0.1.57.0 (QA isolation variant, not production)

- Replace the sale.order inherited view with contextual server actions in QA only, avoiding the `x_total_discount_amount` view validation failure caused during registry rebuild.
- Preserve original sales view source, fields and all business logic unmodified.

# 20.0.1.56.0 - Odoo 20 search-view schema correction

- Make `construction.certification.search` valid in Odoo 20 by removing unsupported attributes from `<search>` and the search `<group>` element.
- Keep existing filter names, domains and grouping contexts, view XML IDs and actions unchanged.
- Regression-checked statically; the module must still be installed and its ORM tests executed on Odoo 20 QA before production use.

# 20.0.1.55.0 - Odoo 20 report registration and test isolation

- Remove the obsolete `report_file` field from all three `ir.actions.report` actions.
- Keep the existing `report_name`, report bindings and external IDs.
- Avoid loading `odoo.tests` in normal runtime by removing the root `tests` import.
- Preserve imports inside `tests/__init__.py` for Odoo test discovery.
- Correct the README title underline for reStructuredText parsing.
- Static verification only: integration tests must be run on Odoo 20 QA.

# 20.0.1.54.0 — revisión económica conjunta (30-10-2026)

- Una certificación sin líneas de trabajo y sin liberación de retención no puede pasar a `measured` ni `approved`, tampoco por RPC o importación directa.
- La preparación de facturas incluye las líneas con base negativa (p. ej. `BC3-BAJA`): solo se omiten movimientos cuyo importe monetario es cero.
- El origen neto de líneas contractuales negativas se mantiene con signo, y los abonos corrigen el saldo en el sentido económico correcto.
- Los descuentos negativos conservan el último céntimo de redondeo al acumular varios períodos, sin duplicar el precio ni modificar lo históricamente aprobado.
- Los cinco cómputos de `account.move.line` (`quantity`, `account_id`, `price_unit`, `tax_ids`, `name`) procesan por separado filas de reversión y filas ordinarias. La recalculación explícita posterior aplica el mismo criterio.
- Nuevo control opcional por compañía: política de aprobación restringida a responsables de ventas o al aprobador designado del proyecto, aplicada desde `write` y desde el botón. El valor predeterminado es `open` para no bloquear bases existentes; activar `restricted` en la compañía después de asignar aprobadores.
- Pruebas ORM nuevas para certificaciones vacías, bajas contractuales y el último céntimo de un coeficiente negativo.

**Pendiente de validación:** pruebas contables ORM, especialmente reversión de facturas con IVA, retenciones, anticipos y pagos conciliados en Odoo 20 Enterprise. No hay una instancia Odoo disponible aquí.

---

# Changelog – tl_construction_certification

## 20.0.1.53.0 — corrections after critical audit

- Load the certification wizard action before the sale order view referencing it.
- Attribute development and maintenance to Tecniloop, not OCA.
- Read cumulative MRP progress only once per sale line, choosing the sale-line total or the maximum of cumulative totals on related MOs; keep displayed percent consistent with quantity and budget.
- Restore availability of quantities returned by posted credit notes in the creation wizard; include standard SO invoicing.
- Keep cumulative origin correct when a certification includes only some of the budget lines; preserve previous work and posted refunds on omitted lines.
- Allow a zero-net invoice if the work is offset by a posted advance.
- Disallow deductions against an advance that has no posted invoice, including advances without tax.
- Prevent cancellation based on a single partial credit note; compare all linked work lines, quantities, rounding, retention, advance applications, their tax totals, and credit-note reversals before unlocking the certification.
- Restore invoiced state when a fully refunding credit note is itself reversed (subject to advance-balance verification).
- Synchronise cancellation of draft construction invoices from Accounting, and exclude cancelled invoices from SO quantities invoiced.
- Validate model-level state transitions and prohibit changing billed invoices, approved certificates, or confirmed advances via direct ORM writes.
- Validate advance and guarantee accounts' accounting types in addition to company membership and reconcilability.
- Replace invalid Spanish PGC test account 560001 (liability) with a generic current-asset test account 449001 (other debtors). The correct customer account remains a company-specific accounting decision.
- Extend tests to cover critical refund, advance, MRP, and state-transition scenarios and adjust legacy fixtures to require posted advance invoices.

### Not included / not verified

- FIEBDC-3/BC3 import was requested historically but is not part of the original code. No sample, mapping specification or work-item source was supplied, so it has not been invented in this bug-fix release.
- Integration tests require Odoo 20 Enterprise and the exact ``construction_developer`` addon; they could not be run in this isolated environment.

### Deployment recommendations

1. Back up the database and update the addon in an isolated staging clone.
2. Install with the exact Odoo 20 core + Enterprise + industry versions used by production.
3. Run `--test-enable` (module tests) and reconcile invoice totals, VAT and customer payments for normal, partially refunded and fully refunded certifications.
4. Verify any existing certifications already marked cancelled after partial refunds before enabling the corrected logic in production.

## QA 20.0.1.58.0 - Regressions (31 Oct 2026)

- Odoo 20 computed snapshots are permitted through the controlled internal compute context without unlocking business edits on approved lines.
- Persistent per-sale certification number counter survives deletion, with existing-DB seed from current rows.
- ORM tests inspect Odoo 20 `get_depends(model)`, MRO-wrapped methods, and either the normal sales view or QA menu action.
- Corrected two internally inconsistent advance-allocation test expectations; business allocation code unchanged.
- Accumulated invoicing, monetary snapshots, tax totals, and refund logic are NOT marked fixed; QA ORM retest required.
- QA-only manifests still exclude the inherited sales order form because of the Odoo Industry manual-field issue.


## QA 20.0.1.59.0 - Approval snapshot flush (31 Oct 2026)

- Force the stored certification line and header snapshots through Odoo 20's
  documented ``flush_recordset`` API **before** the state becomes approved.
- Prevent successful draft values being lost when approved-state computes
  restore still-NULL SQL columns (as observed in the QA finance probe).
- Works for action approval and direct ORM writes; no changes to existing
  approved/invoiced rows and no automatic historic repricing.
- Retains the QA-only Action-menu fallback: sale order form view not loaded.

## 20.0.1.60.0 (QA v8) - Fractional test precision on Odoo 20

- Test-only correction: `test_last_cent_of_negative_contract_coefficient_is_preserved`
  now derives three measured quantities from the installed `Product Unit of Measure`
  precision, guaranteeing that they total exactly one work unit.
- The last period assertion now follows the cumulative monetary rounding
  algorithm, rather than assuming a fixed -33.35 amount across all precisions.
- No changes to models, views, accounting or BC3 business logic from QA v7.
- Only QA fallback menus are loaded, not original inherited sale order views.
