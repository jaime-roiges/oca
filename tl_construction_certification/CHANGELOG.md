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
