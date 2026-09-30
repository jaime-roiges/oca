Adaptacion de los clientes, proveedores y bancos para Espana
==============================================================

Migracion tecnica para Odoo 20 basada en ``l10n_es_partner`` 19.0 de OCA.

Cambios relevantes de Odoo 20
------------------------------

* ``res.bank`` ha sido eliminado del core.
* Los datos de banco se almacenan directamente en ``res.partner.bank``
  (``bank_name``, ``bank_bic``, direccion, pais y ``clearing_number``).
* Por ello el directorio maestro de bancos espanoles y su wizard de importacion
  desde Banco de Espana no tienen equivalencia 1:1 y no se recrean.
* Los antiguos campos descriptivos del banco se conservan por cuenta bancaria
  como ``bank_long_name``, ``bank_vat`` y ``bank_website``.
* Se conserva el campo ``comercial`` y el patron de nombre de contactos.
