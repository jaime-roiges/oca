{
    "name": "Blanket Contracts - Customer Fiscal Advance Invoice",
    "version": "20.0.1.0.0",
    "summary": "Issue a customer advance tax invoice linked to an OCA blanket agreement",
    "category": "Accounting/Accounting",
    "license": "AGPL-3",
    "author": "Tecniloop",
    "website": "https://github.com/jaime-roiges/oca",
    "depends": ["tl_sale_advance_allocation"],
    "data": [
        "security/ir.access.csv",
        "wizard/customer_advance_invoice_views.xml",
    ],
    "installable": True,
}
