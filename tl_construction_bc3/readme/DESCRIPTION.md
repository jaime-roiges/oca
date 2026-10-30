# Descripción funcional

## Catálogos y presupuestos

- Importa conceptos BC3 de tipo 1/4 como productos separados por `bc3.catalog`, `company_id` y código; nunca reutiliza un producto normal por coincidencia de referencia interna.
- Importa presupuestos de tipo 2 como capítulos y partidas de venta. Identifica cada aparición por su ruta jerárquica `bc3_path`, incluso con códigos de concepto repetidos.
- Valida precios, cantidades, redondeos configurados por `~K`, totales detallados `~M`/`~N`, fechas y referencias circulares antes de operar económicamente.
- Modos **estricto** y **compatible** con advertencias para fuentes incompletas. La posición explícita de una medición siempre debe corresponder con la partida real.
- El precio se basa en `~D` por defecto o, si se elige, en `~C`. Permite seleccionar el índice de tarifa de precios y moneda.
- En pedidos borrador, las reimportaciones actualizan líneas por posición, bloqueando cambios de identidad, pérdidas de partidas o renumeraciones ambiguas.
- Conserva el detalle de mediciones en JSON en las líneas de venta y permite incluir coeficientes como líneas separadas, sin importar IVA como producto.
- Conserva las condiciones estándar del presupuesto e importa impuestos aplicando la posición fiscal de Odoo. Los importes de moneda extranjera se conservan en la línea de venta, nunca en `list_price` en moneda de compañía.

## Certificaciones

- Un BC3 tipo 3 siempre expresa cantidades a origen, no el contrato. La cantidad contractual solo procede del pedido Odoo confirmado.
- Calcula `qty_period` restando el origen neto ya aprobado/facturado; admite abonos publicados y bloquea cantidades fuera de contrato o negativas.
- Los borradores reimportados se sustituyen completamente; una corrección de origen que deja incremento cero elimina las líneas obsoletas del borrador.
- Exige un número de certificación válido, correspondencia inequívoca de partidas y bloquea otras certificaciones pendientes para evitar contar dos veces cantidades.

## Auditoría y límites

- Registra cada importación exitosa en `bc3.import.history`, conservando el archivo original, su huella SHA-256, el usuario, fecha, catálogo, destino y advertencias.
- No importa íntegramente documentos `~F`, residuos `~R/~X`, familias paramétricas, etiquetas BIM complejas ni versiones completas de catálogo; tampoco exporta BC3.
- La conformidad FIEBDC-3/2024 es parcial y depende del modo de validación; en particular el modo compatible acepta archivos históricos o incompletos con advertencias.
- No permite modificaciones automáticas del contrato confirmado ni convierte monedas por su cuenta.
- Las pruebas ORM y de contabilidad deben ejecutarse en una base de staging Odoo 20 Enterprise con módulos dependientes instalados.
