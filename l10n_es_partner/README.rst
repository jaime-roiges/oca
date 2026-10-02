============================================================
Adaptación de los clientes, proveedores y bancos para España
============================================================

Migración estática para Odoo 20 del módulo OCA ``l10n_es_partner``.

Funcionalidad mantenida:

* Nombre comercial en contactos/empresas y búsqueda por dicho nombre.
* Patrón configurable para el nombre mostrado mediante
  ``l10n_es_partner.name_pattern``.
* Datos descriptivos de la entidad bancaria sobre ``res.partner.bank``:
  nombre largo, NIF y web.

Cambio estructural de Odoo 20
=============================

Odoo 20 elimina el modelo maestro ``res.bank``. Por ello esta migración retira el antiguo
asistente que importaba el directorio de bancos del Banco de España y traslada los campos
adicionales a ``res.partner.bank``.

Consulte ``MIGRATION_NOTES.md`` para los detalles de migración y las limitaciones.
