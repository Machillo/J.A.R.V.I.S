-- Rollback of 20261001120000_category_suscripciones.sql (manual, human decision).
-- Removes only the catalog row. Rows in other tables that already use the category keep it:
-- review them before rolling back (SELECT category, count(*) ... WHERE category = 'Suscripciones').
BEGIN;
SET LOCAL lock_timeout = '5s';
DELETE FROM public.category_catalog WHERE group_name = 'GASTOS VARIABLES' AND category_name = 'Suscripciones';
COMMIT;
