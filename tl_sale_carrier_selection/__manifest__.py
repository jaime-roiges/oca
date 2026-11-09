{
    'name': 'Cheapest Eligible Carrier Selection',
    'summary': 'Compare Odoo delivery rates and select the cheapest eligible carrier',
    'version': '20.0.2.0.1',
    'category': 'Inventory/Delivery',
    'license': 'AGPL-3',
    'author': 'Tecniloop',
    'website': 'https://github.com/jaime-roiges/oca',
    'depends': ['delivery', 'website_sale'],
    'data': [
        'security/ir.access.csv',
        'views/carrier_selection_views.xml',
        'wizard/carrier_compare_views.xml',
    ],
    'installable': True,
}
