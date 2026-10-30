# Uso y actualización (Odoo 20)

1. Instale `construction_developer` y `sale_management`; instale también `tl_construction_certification` (compatible con esta versión) para importar certificaciones.
2. En **Ventas > Import BC3** o desde el pedido, cargue un BC3. Compruebe el **catálogo de origen**: los conceptos se identifican por catálogo y código; dos catálogos pueden usar el mismo código sin compartir producto.
3. En **Validación** elija:
   - **FIEBDC-3/2024 strict** (predeterminado): exige `~M` para las partidas en documentos de presupuesto/certificación, correspondencia de posiciones y coherencia entre `~D`, `~M` y las mediciones detalladas.
   - **Compatible**: para BC3 antiguos o incompletos. Registra discrepancias; nunca adjudica una posición explícita incorrecta a otra partida. Es responsabilidad del usuario verificar sus advertencias.
4. Indique el **ámbito de precios** de `~C` / `~K` (empezando en 1). Elija el ámbito que coincida con la moneda del pedido. Se rechaza una diferencia de moneda sin conversión explícita.
5. Pulse **Preview**: valida el archivo y presenta las líneas, la base económica orientativa y los avisos. No crea productos, pedidos ni archivos históricos.
6. Seleccione **Use decomposition price** para calcular precios a partir de `~D` (predeterminado), o desactívelo para mantener los precios `~C`. Revise las diferencias indicadas.
7. Active **Apply coefficients** solo si los precios del presupuesto no incorporan los mismos costes indirectos, gastos generales, beneficio o descuentos. El IVA del `~K` no se importa como producto.
8. Para actualizar un presupuesto **en borrador**, seleccione el mismo pedido y la política **Update BC3 lines**. Las líneas se identifican por la posición jerárquica. Si desaparece una partida, se renumera o cambia de código, la importación se bloquea para revisión manual.
9. Para importar un **BC3 tipo 3**, seleccione el contrato **confirmado**. Debe contener número de certificación y cantidades acumuladas de obra. El contrato sigue inmutable. El módulo crea el periodo positivo pendiente como `origen BC3 - origen neto previamente certificado`.
10. Al reimportar la misma certificación aún en borrador, sustituye todas sus líneas. Si el origen nuevo equivale al ya certificado, elimina las líneas pendientes antiguas: no permanece un borrador con cantidades obsoletas. Si un origen disminuye respecto al origen neto comprometido, es necesaria la rectificación por abono antes de importar.
11. Consulte **Ventas > BC3 Import History**: cada importación exitosa conserva el original, SHA-256, usuario, fecha, catálogo, pedido, ámbito y advertencias. **Ventas > BC3 Catalogs** permite gestionar las fuentes.

## Unidades, impuestos, catálogos

- Las unidades como `m³`, `cm` o `km` pueden estar archivadas en Odoo 20; actívelas antes de importar. No se convierten de forma silenciosa.
- En presupuestos con divisa extranjera válida para el pedido, el precio BC3 permanece en la línea de venta; el producto no recibe ese importe extranjero como `list_price` en moneda de compañía. Los catálogos independientes en moneda extranjera se bloquean si no hay conversión.
- La posición fiscal de la venta interviene en los impuestos de las partidas. El porcentaje fiscal informativo del BC3 no sustituye la configuración tributaria de Odoo.
- Los productos BC3 están aislados por catálogo y empresa. Una actualización desde `20.0.1.2.0` puede crear nuevos productos vinculados al catálogo en lugar de reutilizar productos BC3 antiguos sin catálogo; revise el mapeo en staging antes de actualizar presupuestos con líneas antiguas.
- Se conserva el archivo original por importación, pero todavía no hay revisiones de precios por fecha/territorio, ni procesamiento completo de documentos externos FIEBDC.

## Pruebas sin Odoo

Desde la raíz del módulo:

```bash
python -m unittest discover -s tests -v
```

Las pruebas de parser, aritmética y reglas de importación se ejecutan sin Odoo. Las de ORM se omiten si Odoo 20 no está instalado.

## Pruebas necesarias en staging (Odoo 20 Enterprise)

- Instalar/actualizar `tl_construction_bc3` desde `20.0.1.2.0` y verificar vistas, seguridad y archivo histórico.
- Importar dos veces el mismo presupuesto con el mismo catálogo; comprobar partidas, productos, impuestos y bases económicas.
- Importar dos catálogos que utilizan el mismo código para artículos distintos; deben ser productos diferentes.
- Importar con formato estricto y compatible; comprobar fechas, `~K`, unidades, ausencia/discordancia de `~M` y posiciones inválidas.
- Importar contrato de 100 unidades, certificar 40, importar tipo 3 con `~D=~M=70`: segunda certificación 30. Reimportar ese borrador con `~D=~M=40`: el borrador deberá quedar sin líneas.
- Publicar un abono parcial y repetir el origen neto; contrastar el resultado con la contabilidad de `tl_construction_certification`.

Realice copia de seguridad. La validación sintáctica y los tests autónomos no garantizan todavía la instalación funcional o contable.
