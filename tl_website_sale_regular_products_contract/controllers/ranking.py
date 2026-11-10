# Copyright 2026 Tecniloop
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Pure ranking helpers, suitable for static tests without an Odoo database."""


def rank_visible_template_ids(quantity_by_template, visible_template_ids, limit):
    """Sort *visible* products by normalized quantity and stable ID tie break.

    This function is deliberately passed a pre-filtered set of website-visible
    templates. No quantity or template ID from an unrelated customer appears
    in the rendered result.
    """
    if limit <= 0:
        return []
    candidates = (
        template_id
        for template_id in visible_template_ids
        if quantity_by_template.get(template_id, 0.0) > 0.0
    )
    return sorted(
        candidates,
        key=lambda template_id: (-quantity_by_template[template_id], template_id),
    )[:limit]
