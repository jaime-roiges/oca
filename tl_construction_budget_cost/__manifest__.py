{
    'name': 'Construction Budget Costs',
    'version': '20.0.1.0.5',
    'category': 'Construction',
    'summary': 'Per-quotation work item resource costs and indirect overhead',
    'author': 'Tecniloop',
    'license': 'AGPL-3',
    'depends': ['construction_developer', 'sale_margin', 'tl_construction_manual_field_compat'],
    'data': ['security/ir.access.csv', 'views/sale_order_views.xml', 'views/mrp_bom_views.xml', 'views/bom_cost_update_views.xml'],
    'installable': True,
}
