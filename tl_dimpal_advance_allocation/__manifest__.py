{
    'name': 'Dimpal - Fiscal Advances and Partial Allocation',
    'summary': 'Customer and vendor advance invoices, 438/407 and proportional deduction',
    'version': '20.0.2.0.0',
    'category': 'Accounting/Accounting',
    'license': 'AGPL-3',
    'author': 'Tecniloop',
    'website': 'https://github.com/jaime-roiges/oca',
    'depends': ['tl_dimpal_blanket_management', 'account'],
    'data': [
        'security/ir.access.csv',
        'views/advance_views.xml',
        'wizard/advance_apply_views.xml',
        'wizard/advance_register_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
}
