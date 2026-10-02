-- Rollback of 20261002120000_category_semantic_gates.sql (manual, human decision).
-- Removes only the catalog rows. Rows in other tables that already use these categories keep them:
-- review them before rolling back (SELECT category, count(*) FROM transactions WHERE category IN (...) GROUP BY 1).
BEGIN;
SET LOCAL lock_timeout = '5s';
DELETE FROM public.category_catalog
WHERE (group_name, category_name) IN (('GASTOS VARIABLES', 'Viajes y turismo'), ('SIN CLASIFICAR', 'Sin categoría'),
                                      ('COBROS Y VENTAS', 'Cuentas por cobrar'), ('COBROS Y VENTAS', 'Venta de activo'));
COMMIT;
