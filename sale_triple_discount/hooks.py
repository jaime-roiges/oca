# Copyright 2024-Today - Sylvain Le GAL (GRAP)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Preserve pre-existing standard discounts on a fresh module install."""
    _logger.info("Initializing column discount1 on table sale_order_line")
    env.cr.execute(
        """
        UPDATE sale_order_line
           SET discount1 = discount
         WHERE discount != 0
           AND COALESCE(discount1, 0) = 0
           AND COALESCE(discount2, 0) = 0
           AND COALESCE(discount3, 0) = 0
        """
    )
