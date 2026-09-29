# delivery_state 19.0 → 20.0

- Version `20.0.1.1.0`.
- XPath `stock_delivery.view_picking_withcarrier_out_form` //group[@name='carrier_data']: verified in odoo 20.0 addons/stock_delivery/views/delivery_view.xml.
- XPath stock.view_picking_type_form //group[@name='locations']: verified.
- XPath stock.res_config_settings_view_form //setting[@id='stock_move_email']: verified.
- Removed ir.actions.report report_file if present.
- stock.move.line product_uom_id → uom_id in tests only.
- pod_file Binary declared only; no base64 decode to change.
- No res.bank / no redesign.
- Source: OCA/delivery-carrier 19.0.
