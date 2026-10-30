# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def migrate(cr, version):
    """Add the net origin column before the compute reads it.

    Updating an already installed module fails with
    ``column amount_certified_origin_net does not exist`` if the view or
    the compute touches the field before Odoo has altered the table.
    """
    cr.execute(
        """
        ALTER TABLE construction_certification
        ADD COLUMN IF NOT EXISTS amount_certified_origin_net numeric
        """
    )
    cr.execute(
        """
        UPDATE construction_certification
           SET amount_certified_origin_net = amount_certified_origin
         WHERE amount_certified_origin_net IS NULL
        """
    )
