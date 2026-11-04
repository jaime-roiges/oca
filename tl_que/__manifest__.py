{
    'name': 'Tableros de construcción',
    'version': '20.0.1.0.4',
    'category': 'Construction',
    'summary': 'Tableros de construcción en español y precio total alineado con el pedido',
    'description': """
Traduce al español los tableros Naturaleza de coste e Informe de avance.
El precio total suma el importe sin impuestos de cada línea, para que coincida con el pedido.
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
