-- JARVIS Memoria removed: drop memory_items.
--
-- Memoria fed the retired generative chat and was never read by the native apps; the Owner asked
-- (2026-10-25) to remove it completely, its notes included. The backend no longer reads or
-- writes this table (backend/ai/memory_service.py and the /jarvis/memory routes are gone), so
-- its dincr_app grant goes with it (least privilege, backend/tests/test_dincr_app_grants.py).
-- Destructive by decision: the table held 6 Owner notes (checked read-only on 2026-10-25); they are
-- not kept. Profile preferences live in user_preferences and are not touched.
--
-- PRE-APPLY GATE: none for the code (the code no longer uses the table). Apply AFTER the code
-- that removes Memoria is deployed; an older backend would fail only on the removed routes.
-- Apply with backend/scripts/apply_migration.py (BACKUP_VERIFIED) as postgres.
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback: database/rollback/20261025120000_drop_memory_items_rollback.sql (recreates the
-- empty table and its grant; the notes cannot be restored except from a backup).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DROP TABLE IF EXISTS public.memory_items;

COMMIT;

-- Postflight (expect zero rows):
-- SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
--  WHERE n.nspname = 'public' AND c.relname = 'memory_items';
