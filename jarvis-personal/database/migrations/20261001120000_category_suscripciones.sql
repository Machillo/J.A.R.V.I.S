-- Canonical "Suscripciones" expense category (recurring app, streaming and cloud-storage plans).
--
-- The code catalog (backend/finance/category_catalog.py OFFICIAL_CATEGORIES) gains the category;
-- this adds the matching row to category_catalog, which the app reads for its category pickers.
-- Historical rows already use the name (fixed_expenses), so no data is rewritten: existing rows
-- keep their category, and normalize_category maps "Suscripciones" to itself once deployed.
--
-- Additive and idempotent: one INSERT ... ON CONFLICT DO NOTHING. It never updates, drops or
-- deletes. One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
--
-- Preflight (read-only): must return zero rows (the table exists; no row with this name in another group).
--   SELECT 'missing table' WHERE to_regclass('public.category_catalog') IS NULL
--   UNION ALL
--   SELECT 'name used in another group: ' || group_name FROM category_catalog
--   WHERE category_name = 'Suscripciones' AND group_name <> 'GASTOS VARIABLES';
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback (manual, human decision): database/rollback/20261001120000_category_suscripciones_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

INSERT INTO public.category_catalog (group_name, category_name, transaction_type, aliases, is_active, sort_order)
VALUES ('GASTOS VARIABLES', 'Suscripciones', 'expense',
        '["suscripcion", "suscripción", "suscripciones", "subscription", "streaming", "netflix", "spotify"]'::jsonb,
        TRUE, 255)
ON CONFLICT (group_name, category_name) DO NOTHING;

COMMIT;

-- Postflight (read-only): zero rows.
-- SELECT 'missing Suscripciones' WHERE NOT EXISTS (
--   SELECT 1 FROM public.category_catalog
--   WHERE group_name = 'GASTOS VARIABLES' AND category_name = 'Suscripciones' AND transaction_type = 'expense' AND is_active);
