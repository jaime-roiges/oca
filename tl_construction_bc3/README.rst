tl_construction_bc3 - FIEBDC-3/BC3 para Odoo 20
=============================================

Autor: Tecniloop. Licencia: AGPL-3.0 o posterior.
Version: 20.0.1.4.0.

Importador de catálogos de precios y presupuestos FIEBDC-3/2024 a Odoo 20.
Permite importar certificaciones acumuladas sobre un pedido confirmado cuando
se encuentra instalado ``tl_construction_certification``.

**No es un validador completo ni un implementador exhaustivo de FIEBDC-3.**
Solo importa un subconjunto documentado en ``readme/DESCRIPTION.md``.

La importación incluye validación estricta/compatible, selector de ámbito de precios,
catálogos independientes por compañía, conservación de los BC3 originales con SHA-256,
y un botón de previsualización que no crea registros. Se evitan duplicaciones,
modificaciones de contratos confirmados y diferencias silenciosas de moneda. La actualización de productos preexistentes está
deshabilitada por defecto.

Requiere ``construction_developer`` y ``sale_management``.
Para instalar: copia este directorio al addons_path y actualiza la lista de
aplicaciones. Para actualizar una versión previa, utiliza el mismo nombre de
módulo y ejecuta una actualización (-u tl_construction_bc3).

Consulta ``readme/USAGE.md`` para las instrucciones de uso y
``CHANGELOG.md`` para las correcciones. Incluye pruebas Python que se pueden
ejecutar sin Odoo y pruebas ORM pendientes de validar en Odoo 20 Enterprise.

Joint use with tl_construction_certification 20.0.1.54.0
==========================================================

Import the **budget first** in draft and confirm the sales order. If
``Apply coefficients`` is selected, indirect costs, award discount, overheads
and industrial profit are additional contractual sales order lines. They must
not be inserted a second time as normal work items.

Subsequent type-3 BC3 imports must target this same confirmed order. A
certificate with contractual coefficients must include a cumulative ``~M``
for **every** contracted BC3 work item. The assistant values work at the
confirmed order's tax-excluded prices and calculates the new period for
coefficients as the delta between cumulative progress and committed NET
certifications. A file with an incomplete set of work items is rejected,
not apportioned by an arbitrary percentage. A revision to a prior period
must be completed through the ordinary credit-note process before the next
cumulative certificate is imported.

The optional ``Source Catalog Edition`` field separates releases of a price
base whose supplier reuses the same codes. Leave it empty for normal reimports
of an existing catalogue and keep it identical for a confirmed order.

This is a Tecniloop addon, not an OCA-maintained module. Run the Odoo 20
post-install ORM tests in staging before processing real billing documents.
