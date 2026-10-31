## 20.0.1.5.0 (QA isolation variant, not production)

- Replace inherited sale.order view with a contextual BC3 import server action in QA only.
- Preserve BC3 catalog, import wizard and import logic unmodified.

# 20.0.1.4.0 — revisión económica conjunta (30-10-2026)

- El factor de `~D` multiplica también la medición `~M` cuando existe: factor 2 × rendimiento 5 = 10 unidades; se propaga además el factor de capítulos ascendentes y se conservan factor y rendimiento para auditoría.
- Las certificaciones tipo 3 transportan las cantidades efectivas a origen a `tl_construction_certification` y conservan las cantidades contratadas del pedido confirmado.
- Importación de las líneas contractuales BC3-CI, BC3-GG, BC3-BI y BC3-BAJA en cada certificación mediante progreso económico acumulado del trabajo medido, valorado a precios netos del pedido. Se genera solamente la parte no certificada (incluidas líneas de descuento negativas).
- Se exige una cobertura completa de partidas BC3 medidas cuando existen coeficientes: una certificación parcial sin todas las mediciones no puede prorratear importes silenciosamente.
- Se impide que partidas duplicadas se asignen dos veces aunque su primer incremento sea cero.
- Los porcentajes `~K` del BC3 de certificación no modifican el contrato confirmado; las diferencias generan advertencias.
- Se corrigen las fechas fijas de un test ORM y se añaden pruebas del cálculo del factor, capítulos anidados, proporciones de coeficientes y dos certificaciones acumuladas con baja contractual.
- Catálogos con edición explícita opcional (`catalog_edition`): las ediciones elegidas crean espacios de productos distintos sin modificar la restricción SQL histórica de nombre de catálogo.

**Pendiente de validación:** pruebas ORM con Odoo 20 Enterprise, `construction_developer` y `tl_construction_certification` instalados. La cobertura FIEBDC continúa siendo parcial (BIM, residuos, anexos y exportación no completos).

---

# Registro de cambios

## 20.0.1.3.0 - 30-10-2026

- Corrige la interpretación de las certificaciones tipo 3: `~D` y `~M` del fichero reflejan el origen, nunca sustituyen la cantidad contractual confirmada en Odoo.
- En la reimportación de certificaciones en borrador con incremento cero, elimina las líneas obsoletas y vuelve a dejarla en borrador.
- Valida coherencia entre `~D`, `~M`, totales declarados y mediciones detalladas; en modo estricto rechaza errores, en modo compatible informa explícitamente.
- Impide adjudicar a una partida única una `POSICION` `~M` que apunta a otra ruta.
- Añade precisión `~K` extendida/legacy para ámbitos, redondeos HALF_UP de conceptos, factores, rendimientos y dimensiones; selector de ámbito de precios.
- Rechaza fechas `~C` inválidas en modo estricto, advierte en modo compatible.
- Controla importes no finitos/desbordados en entrada, descomposición, expresiones, coeficientes, líneas y totales presupuestarios.
- Valida las unidades de certificación frente a las del contrato y el número del certificado.
- No guarda precios de un BC3 en moneda extranjera como precios generales del producto en moneda de compañía.
- Añade catálogos BC3 por compañía para no compartir productos de distinta procedencia solo por código.
- Añade histórico inmutable con archivo original, SHA-256, compañía, usuario, ámbito, presupuesto y advertencias.
- Actualiza vistas, seguridad `ir.access.csv` de Odoo 20, documentación y muestra BC3 válida en modo estricto.
- Incluye 27 pruebas autónomas de parser/lógica y 6 pruebas ORM pendientes de ejecutar en staging Odoo 20 Enterprise.
- Sigue pendiente: soporte FIEBDC integral, importación completa BIM/documentos/residuos y ejecución integrada contable.

# Registro de cambios

## 20.0.1.2.0 - 30-10-2026

### Instalación y Odoo 20
- Corrige el XMLID de la acción `tl_construction_bc3.action_bc3_import_wizard`.
- Adapta las columnas de la vista de ventas al contenedor `product_and_description` de Odoo 20.
- Utiliza `_has_common_reference()` en las unidades de medida de Odoo 20, en vez del campo retirado `category_id`.
- Informa de unidades de medida archivadas, sin reemplazarlas automáticamente.
- Mantiene las reglas de acceso en el formato `ir.access.csv` de Odoo 20.

### Parser FIEBDC-3
- Aplica asignaciones explícitas de porcentajes a los componentes correspondientes en `~D`.
- Distingue cantidad contractual de medición acumulada en BC3 de certificación, incluso cuando la cantidad del contrato vale exactamente 1.
- Asocia mediciones a la posición jerárquica exacta de `~M` para conceptos repetidos.
- Actualiza referencias de descomposición y medición al renombrar conceptos con `~B`.
- Detecta ciclos de descomposición y árboles de capítulos; limita profundidad de descomposición.
- Rechaza fechas calendario imposibles, valores no finitos, números no válidos y mediciones truncadas.
- Conserva las líneas de medición y su información textual y dimensional.

### Integridad de presupuestos y certificaciones
- Añade `bc3_path` y una restricción SQL que evita dos líneas con idéntica posición dentro del pedido.
- Reimportaciones idempotentes en pedidos borrador con control de eliminación y cambios de código.
- Añade una previsualización sin escrituras en la base de datos.
- Protege productos normales frente a coincidencias de referencias internas.
- Actualización de productos existentes desactivada por defecto.
- Rechaza monedas incompatibles y unidades desconocidas o archivadas sin autorización/activación.
- Conserva los términos comerciales del pedido y registra el resumen de importación por separado.
- Usa la posición fiscal para calcular impuestos de línea.
- Certifica solo el incremento del período respecto al origen neto ya aprobado y bloquea revisiones de contrato implícitas.
- Bloquea importaciones concurrentes sobre el mismo pedido durante el cálculo de la certificación.

### Pruebas
- 15 pruebas autónomas ejecutadas correctamente (parser y reglas de importación).
- 4 pruebas ORM incluidas, pendientes de ejecutar contra Odoo 20 Enterprise.
- Las comprobaciones estáticas no sustituyen las pruebas de integración del ERP.

### Limitaciones
- Soporte parcial FIEBDC-3/2024, sin importación completa de documentos, BIM o residuos, ni exportación BC3.
- La importación de certificaciones necesita `tl_construction_certification` compatible.
- La base `construction_developer` no se ha instalado ni probado en este entorno.
