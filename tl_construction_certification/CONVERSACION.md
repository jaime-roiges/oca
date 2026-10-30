> Archivo histórico de la evolución hasta la versión 20.0.1.48.0.
> Para las correcciones actuales de 20.0.1.53.0, consulte `CHANGELOG.md`.

# Conversación: módulo `tl_construction_certification`

Autor: Tecniloop  
Versión final: 20.0.1.48.0  
Prefijo técnico: `tl_`  
Módulo: `tl_construction_certification`  
Base: Odoo 20, sobre `construction_developer`

## Encargo

Analizar `construction_developer` y desarrollar un módulo auxiliar para certificaciones de obra y facturación a origen. Incluye anticipos, retenciones, liquidación parcial, importación BC3 y una integración más profunda con el avance MRP. El módulo no debe romper `construction_developer`.

## Evolución

El desarrollo se hizo por análisis críticos repetidos y correcciones sucesivas. Cada pasada cerraba fallos de dinero o de contabilidad y dejaba tests de regresión.

Temas que se fueron cerrando:

- APIs de Odoo 20: `_reverse_moves`, `document_tax_mode`, `price_include_override`, `_reconcile_plan`, `copy_data` con `construction_keep_links`.
- Impuestos: no resetear precios de facturas normales, no mapear dos veces, conservar la exención del presupuesto, usar el IVA del producto si la línea de venta no tiene impuestos.
- Cantidad: no colapsar a 1, conservar la cantidad certificada, origen bruto y origen neto separados.
- Importes: no reescribir lo facturado, céntimo de redondeo, importe neto igual al abono real y no a un prorrateo.
- Abonos: valor absoluto de la cantidad, no contar la reversión del abono como otro abono, refrescar el origen abierto y el de la certificación ya facturada.
- Conciliación: desconciliar antes de pasar a borrador o revertir; anticipos y retenciones por signo contrario.
- Estados: aprobar no deja quieto el importe si no se congela; no marcar facturada sin factura.
- Cuentas de compañía: anticipo (pasivo corriente) y retención (activo corriente), de la compañía y conciliables.

## Fila facturada y fila neta

La ficha no mezcla las dos.

- Facturado: `qty_origin`, `percent_origin`, `amount_origin`. No se mueve al abonar.
- Neto: `qty_origin_net`, `percent_origin_net`, `amount_origin_net`. Baja con el abono publicado. El céntimo de redondeo entra en el importe, no en la cantidad. Un abono revertido no cuenta.

## Tests añadidos

Regresión de cada bug cerrado y casos de uso del README:

1. Pedido confirmado con proyecto.
2. Botón Crear certificación y asistente.
3. Fecha e importación del avance MRP.
4. Cantidad y porcentaje del periodo alineados; el avance MRP es referencia.
5. Retención distinta del 5 %.
6. Cuentas de anticipo y retención: tipo, compañía, conciliable, obligatorias antes de facturar anticipo, retención o liquidación.
7. Aplicar anticipo pendiente: no mueve la línea elegida, baja desde el más nuevo, se para en el neto, base excluida y mismos impuestos en la deducción.
8. Abonos parciales que se suman y refrescan el origen abierto.

## Versiones relevantes

- 20.0.1.24.0 a 20.0.1.36.0: origen neto, importe real del abono, céntimo, reversión del abono.
- 20.0.1.37.0 a 20.0.1.40.0: tests publicables en Odoo 20 y desconciliación completa.
- 20.0.1.41.0 a 20.0.1.48.0: abonos parciales y casos de uso 1 a 7.
- 20.0.1.48.0: copia con prefijo `tl_` y autor Tecniloop.

## Limitación conocida

Los tests no se han ejecutado sobre una instancia de Odoo 20 en esta conversación. Están escritos para esa versión: cuenta de ingreso, sin impuestos en el abono de prueba, desconciliación antes de `button_draft` o `_reverse_moves`, y cantidad positiva al publicar.
