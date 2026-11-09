{
    'name': 'Blanket Contracts - Customer Portal and Release Requests',
    'version': '20.0.1.1.0',
    'summary': 'Customer sees OCA blanket balances and requests delivery on shared sales orders',
    'category': 'Website/Website',
    'license': 'AGPL-3',
    'author': 'Tecniloop',
    'website': 'https://github.com/jaime-roiges/oca',
    'depends': ['portal', 'website', 'tl_sale_advance_allocation'],
    'data': ['security/ir.access.csv', 'views/portal_templates.xml', 'views/release_request_views.xml'],
    'installable': True,
}
