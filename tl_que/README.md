# TL Que - Fix Cost Nature Dashboard

Módulo que corrige el tablero **Cost Nature** del módulo `construction_developer`.

## Problema

El pivot original calculaba:

```
Total Price = Suma Costes / (1 - Media de Margin %)
```

Esto es incorrecto cuando las líneas tienen márgenes diferentes, por lo que el Total Price no coincidía con el total del pedido de venta.

## Solución

- **Total Price**: suma directa del campo `Total Price` ya calculado correctamente por línea.
- **Margin**: `Total Price - Total Cost`.
- **Margin (%)**: `Margin / Total Price` (margen real ponderado).

## Instalación

1. Copia la carpeta `tl_que` en tu directorio de addons.
2. Actualiza la lista de aplicaciones.
3. Instala el módulo **TL Que - Fix Cost Nature Dashboard**.

El dashboard Cost Nature se actualizará automáticamente con la versión corregida.

## Dependencias

- `construction_developer`
- `spreadsheet_dashboard`
