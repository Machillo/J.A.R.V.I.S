-- MANUAL rollback of 20260925140000_financial_ownership_integrity.sql.
-- Human decision only; never run automatically. No financial row is deleted.
--
-- How to run it (apply_migration.py refuses files outside database/migrations,
-- and docs/security/migration-safety-protocol.md §2 allows this exception):
--   1. BACKUP_VERIFIED gate open for this database (db_backup_verify.py gate);
--   2. a second person reads this file and the reason for rolling back;
--   3. psql -v ON_ERROR_STOP=1 over a direct session connection as postgres,
--      one transaction (this file's BEGIN/COMMIT); run step 2 only if decided.
--
-- Step 1 (always): remove the write and delete guards (triggers, CHECK, parent
-- FK and its unique index). The read-only audit functions, the snapshots, the
-- repair log and the delete log are kept as evidence.
--
-- Step 2 (optional): undo the automatic repairs of ONE run. Replace
-- <RUN_ID> with financial_ownership_repair_log.run_id and uncomment the block.
-- Only rows whose workspace_id still equals the logged new value are reverted.

BEGIN;

-- Its ALTERs lock each guarded table: never queue behind traffic for long.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $$
DECLARE
    cfg RECORD;
BEGIN
    -- A second run finds the list function already dropped: nothing to do here.
    IF to_regprocedure('public.dincr_delete_guard_tables()') IS NOT NULL THEN
        FOR cfg IN SELECT * FROM public.dincr_delete_guard_tables() LOOP
            IF to_regclass(format('public.%I', cfg.table_name)) IS NULL THEN
                CONTINUE;
            END IF;
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
                           'trg_' || cfg.table_name || '_delete_guard', cfg.table_name);
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
                           'trg_' || cfg.table_name || '_truncate_guard', cfg.table_name);
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
                           'trg_' || cfg.table_name || '_workspace_move_guard', cfg.table_name);
        END LOOP;
    END IF;
    FOR cfg IN SELECT * FROM public.dincr_ownership_tables() LOOP
        IF to_regclass(format('public.%I', cfg.table_name)) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
                       'trg_' || cfg.table_name || '_ownership_guard', cfg.table_name);
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
                       'trg_' || cfg.table_name || '_delete_guard', cfg.table_name);
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I',
                       'trg_' || cfg.table_name || '_truncate_guard', cfg.table_name);
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I',
                       cfg.table_name, 'ck_' || cfg.table_name || '_workspace_required');
        EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT IF EXISTS %I',
                       cfg.table_name, 'fk_' || cfg.table_name || '_parent_workspace');
    END LOOP;
    FOR cfg IN SELECT DISTINCT parent_table FROM public.dincr_ownership_tables() WHERE parent_table IS NOT NULL LOOP
        -- Only the indexes the migration created (it marks them); a pre-existing
        -- index with the same name is kept.
        IF to_regclass(format('public.%I', 'uq_' || cfg.parent_table || '_id_workspace')) IS NOT NULL
           AND obj_description(to_regclass(format('public.%I', 'uq_' || cfg.parent_table || '_id_workspace')), 'pg_class')
               = 'dincr-ownership-guard' THEN
            EXECUTE format('DROP INDEX public.%I', 'uq_' || cfg.parent_table || '_id_workspace');
        END IF;
    END LOOP;
END $$;

DROP TRIGGER IF EXISTS trg_users_legacy_delete_guard ON public.users;
DROP TRIGGER IF EXISTS trg_allowed_users_legacy_delete_guard ON public.allowed_users;
DROP TRIGGER IF EXISTS trg_accounts_bulk_delete_guard ON public.accounts;
DROP TRIGGER IF EXISTS trg_workspaces_bulk_delete_guard ON public.workspaces;
DROP FUNCTION IF EXISTS public.dincr_guard_financial_ownership();
DROP FUNCTION IF EXISTS public.dincr_guard_financial_delete();
DROP FUNCTION IF EXISTS public.dincr_guard_financial_truncate();
DROP FUNCTION IF EXISTS public.dincr_guard_legacy_identity_delete();
DROP FUNCTION IF EXISTS public.dincr_guard_identity_bulk_delete();
DROP FUNCTION IF EXISTS public.dincr_guard_workspace_move();
DROP FUNCTION IF EXISTS public.dincr_delete_guard_tables();

-- Step 2 (optional):
-- DO $$
-- DECLARE
--     l RECORD;
-- BEGIN
--     FOR l IN
--         SELECT table_name, row_id, new_value
--         FROM public.financial_ownership_repair_log
--         WHERE run_id = '<RUN_ID>'::uuid AND column_name = 'workspace_id'
--     LOOP
--         EXECUTE format('UPDATE public.%I SET workspace_id = NULL WHERE id = $1 AND workspace_id::TEXT = $2', l.table_name)
--         USING l.row_id, l.new_value;
--     END LOOP;
-- END $$;

COMMIT;
