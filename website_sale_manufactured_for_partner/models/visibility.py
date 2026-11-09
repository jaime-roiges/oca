# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Customer identity helpers; intentionally not tied to shipping/billing addresses."""


def allowed_partner_ids(partner):
    if not partner:
        return []
    commercial = partner.commercial_partner_id
    return list({partner.id, commercial.id})


def commercial_customer_matches(user_partner, order_partner):
    """A portal account can checkout only for its own commercial company."""
    return bool(
        user_partner
        and order_partner
        and user_partner.commercial_partner_id == order_partner.commercial_partner_id
    )
