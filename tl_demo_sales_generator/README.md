# tl_demo_sales_generator - Odoo 20.0

Synthetic **sales orders, purchase orders and CRM opportunities with activities**
using existing partners, product variants and internal users. It never creates
master data and all documents carry `tl_demo_generation_run_id`.

## Defaults

| Setting | Default |
| --- | --- |
| Sales orders | 1000, confirmed |
| Purchase orders | 250, unconfirmed RFQs |
| CRM opportunities | 300 |
| Activities per CRM opportunity | 1 to 3 |
| Synthetic date period | Last 12 months |
| Lines per sale/purchase | 1 to 5, unique random products |
| Units per line | 1 to 20 |
| Purchase price | Uniform random 60%-80% of the product sales list price |
| Batch size | 20 documents |

All counts and thresholds are configurable; 0 disables a generator.

## Install

1. Copy this directory into your Odoo 20 `addons_path`.
2. Restart Odoo and refresh the Apps list.
3. Install `tl_demo_sales_generator` (requires `sale_management`, `purchase`,
   `crm` and `mail`).
4. Log in as a **Settings administrator**, open **Demo Data Generator >
   Generate data**, select the company and read the warning.
5. Set counts, dates, filters and check the test-database acknowledgement.
6. Start generation. A background scheduled action processes the documents in
   batches. See **Demo Data Generator > Generation batches** for progress,
   errors and links to records.

Optional: Click **Process one batch** to test a small batch manually. An
administrator can cancel or resume an incomplete batch; it does not delete
records already generated. No uninstallation cleanup of generated documents is
performed. The scheduled action works only when cron workers are enabled.

## Price calculation

For every purchase order line:

    purchase_price = round_currency(
        sales_list_price_in_purchase_uom * uniform(0.60, 0.80)
    )

Example: product sale list price EUR 100 per unit -> purchase line unit price
EUR 60-80. For purchasing in a larger UoM, the product base sales list price
is first converted to the purchase UoM. POs use company currency to avoid
invalid comparisons with vendor currency. Note that Odoo currency rounding
can cause tiny deviations around the percentage limits.

Supplier selection is random across eligible existing suppliers; it is not
restricted by `product.supplierinfo`. This is a demo generator, not an actual
buying recommendation.

## CRM

Each opportunity uses an existing random customer, a random sellable product
in the title and `tl_demo_product_id`, and a random internal user as salesperson.
It creates 1-3 random activity types (eligible generic or CRM-specific default
and phonecall types) with independently selected internal users and deadlines
within the next 60 days. The synthetic reference date appears in the CRM notes
and drives the opportunity's expected closing date; **Odoo's audit field
`create_date` remains the actual creation timestamp** (CRM historic creation
reports are not simulated).

## Safety and data hygiene

- **Disposable test databases only.** Administrator-only menu and ORM guard.
- Sale confirmation invokes standard `action_confirm`; this can create deliveries,
  procurements, MRP activities, automations, or notifications in other modules.
  Purchase confirmation, if enabled, can create receipts and is subject to
  Odoo's approval rules. Do not enable either on production.
- Sales, purchases and CRM activities may trigger effects in installed custom
  modules despite mail tracking suppression.
- The module does **not** validate deliveries, create/post invoices or bills,
  or create new customers, vendors, products or users itself.
- Date fields in sale and purchase documents are backdated, while journal,
  stock, logs and `create_date` audit timestamps are not backdated.
- Existing vendor prices and product costs are left unchanged.
- A savepoint isolates each document so a failure does not roll back a whole
  batch. After 10 consecutive failures the batch is paused. The last error is
  displayed, with more information in the server log. Failed items are counted
  as attempted and are not automatically retried.
- Deleting a generation batch is disabled. No mass deletion of generated
  confirmed documents is offered (they may have dependent business records).

## Functional smoke test

In a staging Odoo 20 with the required apps and at least one active customer,
supplier, sellable product, purchasable product and internal CRM user:

1. Queue **2 sales (unconfirmed)**, **2 purchases (unconfirmed)** and **2 CRM**
   opportunities with **1-2 activities**.
2. Use Process one batch or enable cron workers.
3. Confirm that the batch reaches Done and that every generated document has
   the expected run ID.
4. Verify that each purchase line price matches the configured percentage of
   the product sales list price (in purchase UoM).
5. Confirm that no new partners/products/users were created, and activities
   refer to the generated CRM opportunities.
6. Only after the above succeeds, test a confirmed sales order in staging.

## Test command (existing Odoo instance)

    ./odoo-bin -c /path/odoo.conf -d your_test_db --test-enable \
      --test-tags /tl_demo_sales_generator --stop-after-init \
      -u tl_demo_sales_generator --no-http

This package was syntax/XML-checked outside Odoo; final installation and
business-flow testing require a running Odoo 20 staging instance.

## Correccion 20.0.1.0.1

Se especifican tablas relacionales independientes para los filtros Many2many de clientes, proveedores, productos y usuarios, tanto en el asistente como en el modelo de lotes. Corrige el error de instalacion de Odoo 20 `Many2many fields tl.demo.generation.run.vendor_ids and tl.demo.generation.run.customer_ids use the same table and columns`.

En una instalacion fallida, sustituir el codigo del addon, reiniciar Odoo, actualizar la lista de aplicaciones y volver a instalar. No es necesario borrar la base de datos.

## Odoo 20 security format (20.0.1.0.3)

Odoo 20 uses `ir.access` instead of `ir.model.access` / `ir.rule`. This addon
ships `security/ir.access.csv` with `model_id`, `group_id/id`, `operation` and
`domain` and keeps the manager-only policy (`base.group_system`). The run model
allows `cru` (no delete) and the transient wizard allows `crud`.
The fix for all eight unique Many2many relation tables in 20.0.1.0.1 remains.

**Note:** Python compilation, XML/CSV structural verification and archive tests
do not substitute for an installation on a live Odoo 20 database.

## Compatibility note - Odoo 20 search views (20.0.1.0.3)

The grouping filters on the batch search view use a plain `<group>` tag.
Odoo 20 does not accept legacy `expand` or `string` attributes on a
search-view `<group>`. This is independent of the previous fixes to
Many2many relation tables and `ir.access` permissions.
The included `tools/check_odoo20_static.py` checks XML and this rule
without requiring an Odoo database.
