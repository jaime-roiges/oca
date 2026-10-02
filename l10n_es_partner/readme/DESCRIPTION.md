Incluye la siguiente funcionalidad en Odoo 20:

- Añade el campo *Nombre comercial* a las empresas y permite buscar por él.
- Permite definir un patrón del nombre mostrado a partir del nombre y el nombre comercial.
- Añade nombre largo, NIF y web de la entidad bancaria a `res.partner.bank`.

Odoo 20 ya no dispone del modelo maestro `res.bank`. Por ello se ha retirado el antiguo
asistente de importación del directorio de bancos del Banco de España, que en Odoo 19
creaba registros `res.bank`.
