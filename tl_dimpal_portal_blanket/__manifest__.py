{
    'name': 'Dimpal - Customer Supply Contract Portal',
    'summary': 'Customer portal for dedicated contract stock, deliveries and advance balances',
    'version': '20.0.2.0.0',
    'category': 'Website/Website',
    'license': 'AGPL-3',
    'author': 'Tecniloop',
    'website': 'https://github.com/jaime-roiges/oca',
    'depends': ['portal', 'website', 'tl_dimpal_advance_allocation'],
    'data': [
        'security/ir.access.csv',
        'views/portal_templates.xml',
        'views/release_request_views.xml',
    ],
    'installable': True,
}
