# Dimpal Odoo 20 - Corrección de dominio JSON y localización es/ca

Fecha: 9 de noviembre de 2026. **Candidato para QA**, no certificado en ejecución.

## Incidencia 1: error en cambio de pedido de venta

Traceback: `TypeError: sale.order.blanket_order_id_domain: use BinaryValue instead of list`.

Corregido en `sale_order_blanket_order/models/sale_order.py`:

- `fields.Binary` -> **`fields.Json`** para el dominio computado del selector de pedidos marco. Odoo 20 ya usa `fields.Json` para dominios dinámicos de formularios.
- Eliminada la referencia accidental a `self.partner_id` dentro del bucle: se usa `order.partner_id`.
- Añadidas dependencias al cálculo por `date_order` y `partner_shipping_id` para que se actualice al cambiar cliente, dirección o fechas.
- Incorporada una prueba de regresión que evalúa el campo en pedidos `call_off` y ordinarios sin necesidad de flujo de albarán.
- Versión de `sale_order_blanket_order`: `20.0.1.0.1`.

El campo no es almacenado (`store=False` por defecto), por lo que esta corrección no requiere alterar tablas ni migrar datos binarios.

## Incidencia 2: traducciones insuficientes

Se ha regenerado `i18n/es.po` e `i18n/ca.po` para **los 13 addons incluidos**. Se han conservado las traducciones previas válidas y se han reintroducido las referencias `#: ...` a campos, selecciones, código y vistas (Odoo 20 las necesita para importar las traducciones). Odoo recomienda mantener las referencias de las plantillas `.pot` originales.

| Addon | es.po | ca.po |
|---|---:|---:|
| product_sale_manufactured_for | 2/2 | 2/2 |
| purchase_deposit | 48/48 | 48/48 |
| sale_manual_delivery | 48/48 | 48/48 |
| sale_order_blanket_order | 116/116 | 116/116 |
| sale_order_blanket_order_stock_prebook | 5/5 | 5/5 |
| sale_stock_prebook | 18/18 | 18/18 |
| sale_stock_reference_by_line | 5/5 | 5/5 |
| tl_dimpal_advance_allocation | 45/45 | 45/45 |
| tl_dimpal_blanket_management | 9/9 | 9/9 |
| tl_dimpal_carrier_selection | 16/16 | 16/16 |
| tl_dimpal_portal_blanket | 35/35 | 35/35 |
| tl_dimpal_website_contract_checkout | 9/9 | 9/9 |
| website_sale_manufactured_for_partner | 7/7 | 7/7 |
| **Total** | **363/363** | **363/363** |

**Alcance de cobertura:** 100 % de los **363 mensajes identificados** en las plantillas OCA facilitadas y en las cadenas de Python/XML extraídas de los 13 addons del paquete. No supone que se hayan validado visualmente *todas* las pantallas, ni incluye las traducciones de Odoo estándar, Enterprise o del addon externo `website_sale_checkout_skip_payment` (cuyo código no se aportó).

## Validaciones realizadas

- Compilación estática de Python, XML, manifiestos y CSV del paquete.
- 26 catálogos `es.po` y `ca.po` parseados con Babel y comprobados para garantizar que cada mensaje tenga al menos una referencia de origen y `#. module:`.
- Concordancia de los identificadores de formato (`%(variable)s`, `%s`) entre `msgid` y `msgstr`, y etiquetas HTML compatibles.
- Las traducciones no están probadas en la interfaz real ni se ha ejecutado una instalación de Odoo 20 Enterprise.

## Aplicación sugerida

1. Hacer copia de seguridad del código y de la base de datos de QA.
2. Extraer el parche mínimo **desde el directorio que contiene los 13 addons**, de modo que se sustituyan sus directorios `i18n/` y los archivos modificados de `sale_order_blanket_order`.
3. Reiniciar el servicio y actualizar el módulo `sale_order_blanket_order` y los módulos de los que se quiera recargar traducciones. Verificar que los idiomas **Español (es_ES)** y **Catalán (ca_ES)** estén instalados/activados.
4. Si hay traducciones ya importadas que no cambian, recargarlas con la opción de Odoo `--i18n-overwrite` **en QA y con respaldo**, pues puede sobrescribir traducciones personalizadas.
5. Probar el formulario de pedido, cambio de cliente, selección de comanda marc, vistas y portal en ambos idiomas.

**No requiere instrucciones SQL ni modificaciones directas a PostgreSQL.**
