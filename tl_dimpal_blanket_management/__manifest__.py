{
    'name': 'Dimpal - OCA Blanket Order Integration',
    'version': '20.0.2.0.0',
    'summary': 'Thin Dimpal extension for OCA sale.order blanket agreements',
    'author': 'Tecniloop',
    'website': 'https://github.com/jaime-roiges/oca',
    'category': 'Sales/Sales',
    'license': 'AGPL-3',
    'depends': ['sale_order_blanket_order', 'purchase_stock'],
    'data': [
        'views/blanket_views.xml',
        'views/purchase_views.xml',
    ],
    'installable': True,
    'application': False,
}
