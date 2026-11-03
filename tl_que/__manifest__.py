{
    'name': 'TL Que - Fix Cost Nature Dashboard',
    'version': '20.0.1.0.3',
    'category': 'Construction',
    'summary': 'Corrige el tablero Cost Nature para que el Total Price coincida con el pedido',
    'description': """
Corrige el dashboard Cost Nature del módulo construction_developer.

Problema original:
- El pivot recalculaba Total Price como Coste / (1 - media de márgenes)
- Esto provocaba que el Total Price no coincidiera con el total del pedido de venta

Solución:
- Total Price se suma directamente del campo ya calculado correctamente por línea
- Margin = Total Price - Total Cost
- Margin (%) = Margin / Total Price (margen real ponderado)
    """,
    'author': 'TL',
    'depends': [
        'construction_developer',
        'spreadsheet_dashboard',
    ],
    'data': [
        'data/spreadsheet_dashboard.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
