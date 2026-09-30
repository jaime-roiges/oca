def pre_init_hook(env):
    """Keep the legacy cron XML-ID without creating a duplicate cron.

    Odoo 20 moved the VIES cron from base_vat to l10n_eu_account_vies.  A
    legacy addon can still refer to ``base_vat.vies_iap_check_update``.  Make
    that XML-ID an alias of the Odoo 20 cron.  On an upgraded database, disable
    the old cron first if it is still present as a distinct record.
    """
    target = env.ref(
        "l10n_eu_account_vies.vies_iap_check_update",
        raise_if_not_found=False,
    )
    if not target:
        return

    imd = env["ir.model.data"].sudo()
    legacy = imd.search(
        [("module", "=", "base_vat"), ("name", "=", "vies_iap_check_update")],
        limit=1,
    )

    if legacy and legacy.model == "ir.cron" and legacy.res_id != target.id:
        old_cron = env["ir.cron"].sudo().browse(legacy.res_id).exists()
        if old_cron:
            old_cron.active = False

    values = {
        "module": "base_vat",
        "name": "vies_iap_check_update",
        "model": target._name,
        "res_id": target.id,
        "noupdate": True,
    }
    if legacy:
        legacy.write(values)
    else:
        imd.create(values)
