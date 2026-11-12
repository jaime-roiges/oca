# Deducción proporcional de facturas de anticipo — Odoo 20

**Módulo:** `tl_sale_downpayment_proportional`  
**Versión:** `20.0.1.0.1`  
**Licencia:** AGPL-3  
**Dependencias:** `sale` (y dependencias estándar de Odoo)

## Qué cambia

Al facturar parcialmente productos de un pedido, marcando **Deducir anticipos**, Odoo estándar incluye la totalidad de las facturas de anticipo pendientes. Este módulo recalcula únicamente las líneas negativas de anticipo de **esa nueva factura**, dejando intactas las facturas de anticipo positivas ya emitidas y sus cuentas.

La deducción de cada factura corresponde a la fracción de base imponible de los productos que representa sobre el total del pedido. En la última factura se ajusta el redondeo, con el límite del anticipo disponible y de la base neta/bruta de la factura.

## Ejemplo sin IVA

| Documento | Productos | Anticipo consumido | Base a facturar |
|---|---:|---:|---:|
| Factura de anticipo inicial | — | — | 3.000 € |
| Factura parcial 1 | 2.000 € | -600 € | 1.400 € |
| Factura parcial 2 | 3.000 € | -900 € | 2.100 € |
| Factura parcial 3 | 5.000 € | -1.500 € | 3.500 € |

## Instalación

1. Copie la carpeta `tl_sale_downpayment_proportional` al `addons_path` de su Odoo 20.
2. Actualice la lista de aplicaciones e instale **Sale Down Payment Proportional Deduction**.
3. Cree un pedido de 10 unidades de un producto facturable al entregar.
4. Emita la factura de anticipo (por ejemplo, 30 %) con el asistente estándar de Odoo y contabilícela.
5. Facture sucesivamente entregas de 2, 3 y 5 unidades marcando **Deducir anticipos**.
6. Compruebe que las líneas negativas de anticipo consumen 20 %, 30 % y 50 % del anticipo original, respectivamente.

Si no marca **Deducir anticipos**, el comportamiento sigue siendo el estándar: no aplicar deducción.

## Tests en una base de pruebas

```bash
odoo-bin -d <base_pruebas> --stop-after-init --test-enable \
  --test-tags /tl_sale_downpayment_proportional \
  -i tl_sale_downpayment_proportional
```

Pruebas de integración incluidas: porcentajes, anticipo fijo, varios anticipos, desactivar deducción, anulación de borrador, facturación consolidada e IVA al 21 %. Estas pruebas requieren un **Odoo 20 real con PostgreSQL**; no han podido ejecutarse en el entorno de creación del paquete.

## Alcance y precauciones

- Trabaja con **facturas de anticipo nativas** de `sale.advance.payment.inv`, no con pagos contables anticipados de `OCA/sale_advance_payment`.
- El anticipo puede estar cobrado o pendiente de cobro: el módulo respeta el criterio estándar de Odoo para seleccionar anticipos; **no exige** conciliación ni estado «Pagado».
- Los borradores posteriores también reservan anticipo hasta su anulación. Los documentos ya emitidos antes de instalar el módulo **no se modifican**.
- El módulo conserva `extra_tax_data` y lo escala para mantener el desglose impositivo de Odoo 20. **Impuestos incluidos en precio, múltiples tipos de IVA, recargos, rectificativas y localización española requieren validación específica antes de producción.**
- No aplica deducciones a una línea que mezcle pedidos distintos; devuelve un mensaje de error por seguridad.
- No modifique manualmente las deducciones ni sus datos fiscales sin revisar la trazabilidad y el saldo: el módulo no intercepta esas modificaciones posteriores.

La prueba automática de cálculo sin Odoo se entrega en el archivo independiente `offline_qa.py` en la carpeta de documentación adjunta al ZIP de distribución.

## Corrección 20.0.1.0.1 — 12/11/2026

- Corregidos los comentarios de origen de cada entrada de `i18n/es.po` a
  `#. module: tl_sale_downpayment_proportional`, `#. odoo-python` y
  `#: code:addons/tl_sale_downpayment_proportional/models/sale_order.py:0`.
  El importador de Odoo 20 exige esa referencia para resolver el módulo.
- Sin cambios en la lógica del anticipo en esta revisión.
- Permisos Odoo 20: el módulo solo hereda `sale.order`, sin crear modelos
  ni reglas de seguridad. Por eso no necesita `security/ir.access.csv`.
  No debe incluirse el formato obsoleto `ir.model.access.csv`.

**Si la instalación anterior falló:** reemplazar la carpeta del módulo
por esta versión, reiniciar Odoo si corresponde y volver a instalar.
No crear permisos nuevos de forma artificial para resolver este error.
