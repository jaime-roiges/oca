# account_banking_pain_base 20.0

- Fuente: módulos del usuario (oca-20.0.zip).
- Fix: Odoo 20 safe_eval no permite acceso a atributos de registros.
  _prepare_field ahora hace fallback a resolución simple de paths
  (obj.attr.sub or other.attr) cuando safe_eval falla.
- Cubre Nombre del deudor (holder_name), company name, direcciones, etc.
- Sin rediseño de la lógica SEPA.
