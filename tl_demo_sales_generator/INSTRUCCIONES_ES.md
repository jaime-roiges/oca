# Guía de instalación y uso - Odoo 20

**Módulo:** `tl_demo_sales_generator` (20.0.1.0.2)

## Configuración predeterminada

- 1.000 pedidos de venta confirmados en los últimos 12 meses.
- 250 solicitudes de presupuesto de compra (sin confirmar por defecto).
- 300 oportunidades CRM; de 1 a 3 actividades por oportunidad.
- Clientes, proveedores, productos y usuarios seleccionados entre los existentes.
- Entre 1 y 5 líneas por pedido; cantidades de 1 a 20.
- Cada precio unitario de compra se fija aleatoriamente entre el 60 % y el
  80 % del precio de venta del producto, ajustando la unidad de medida.

**Todos los importes y cantidades son configurables.** Se puede poner cero
para desactivar cualquiera de los tres generadores.

## Instalación

1. Descomprimir el ZIP dentro del directorio incluido en `addons_path`.
2. Reiniciar Odoo 20, actualizar la lista de aplicaciones e instalar el módulo.
3. Abrir el menú principal **Demo Data Generator > Generate data** con un
   usuario Administrador de Ajustes.
4. Revisar fechas, cantidades, confirmación de pedidos y filtros.
5. Marcar la casilla de aceptación de base de datos de pruebas.
6. Pulsar **Start generation**. Consultar **Generation batches** para ver avance,
   errores y acceder a los documentos creados.

La generación se procesa por lotes mediante `ir.cron`. Requiere tener
habilitados los trabajadores cron de Odoo. En una base de pruebas se puede
pulsar **Process one batch** para verificar un lote pequeño.

## Seguridad y consideraciones

- No ejecutar en producción. Se requiere acceso de Administrador de Ajustes.
- Confirmar ventas puede generar entregas, aprovisionamientos, actividades
  de fabricación y automatizaciones. El generador no valida albaranes ni
  contabiliza facturas.
- Por defecto las compras quedan como solicitudes de presupuesto; si se
  activa su confirmación, se respetan las validaciones habituales de Odoo.
- La fecha del documento de venta/compra se simula dentro del periodo. La
  fecha técnica de creación (`create_date`) no se modifica.
- Las oportunidades llevan el producto en el título y un campo relacionado.
  Sus actividades tienen plazos futuros y usuarios internos aleatorios.
- No se altera el precio de coste del producto ni las tarifas de proveedor.
- Cada documento generado se vincula a su lote; no se incorpora un borrado
  masivo de pedidos confirmados debido a sus posibles dependencias.

## Comprobación recomendada

Empezar en una copia de la BD con 2 ventas **sin confirmar**, 2 compras
**sin confirmar** y 2 oportunidades con 1-2 actividades. Revisar los
porcentajes de compra y las asociaciones de clientes, productos y usuarios
antes de ejecutar los 1.000 pedidos confirmados.

El ZIP se ha comprobado sintácticamente fuera de Odoo; aún es
necesaria una prueba de instalación y funcionamiento en una instancia
real de Odoo 20.

## Correccion 20.0.1.0.1

Se especifican tablas relacionales independientes para los filtros Many2many de clientes, proveedores, productos y usuarios, tanto en el asistente como en el modelo de lotes. Corrige el error de instalacion de Odoo 20 `Many2many fields tl.demo.generation.run.vendor_ids and tl.demo.generation.run.customer_ids use the same table and columns`.

En una instalacion fallida, sustituir el codigo del addon, reiniciar Odoo, actualizar la lista de aplicaciones y volver a instalar. No es necesario borrar la base de datos.

## Corrección 20.0.1.0.2 (Odoo 20)

Odoo 20 elimina los modelos `ir.model.access` e `ir.rule`, y unifica el
control de acceso en `ir.access`. Se sustituye el fichero antiguo
`security/ir.model.access.csv` por `security/ir.access.csv` y se adapta
el manifiesto. Los permisos mantienen el alcance original:

- `tl.demo.generation.run`: `cru` para `base.group_system` (sin borrado).
- `tl.demo.generation.wizard`: `crud` para `base.group_system`.

La corrección de relaciones Many2many introducida en 20.0.1.0.1 se conserva.
Para instalaciones fallidas: sustituir *toda* la carpeta del módulo
(sin mezclar archivos), reiniciar el servicio Odoo, actualizar aplicaciones e
instalar de nuevo. Verificar que NO queda `security/ir.model.access.csv`.
No hay que borrar tablas ni registros de la base de datos.

No se ha podido instalar el módulo en un servidor Odoo 20 desde este entorno;
las comprobaciones realizadas son estáticas.
