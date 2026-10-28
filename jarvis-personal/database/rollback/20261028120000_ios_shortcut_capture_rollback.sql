-- MANUAL rollback of 20261028120000_ios_shortcut_capture.sql.
-- Human decision only; never run automatically.
--
-- Precondition: the code that issues Shortcuts tokens and captures Apple Pay / bank SMS candidates
-- is rolled back first.
--
-- What it does: drops shortcut_tokens (every Shortcuts link stops working; users activate it again
-- after a reapply) and the capture-key index, and restores email_message_id NOT NULL. It never
-- deletes a candidate: if any candidate has no email (captured by Shortcuts), it ABORTS without
-- changing anything. A person must first decide, with the user, what happens to those candidates.
--
-- How to run it (docs/security/migration-safety-protocol.md §2): BACKUP_VERIFIED gate open, a
-- second person reads this file, psql -v ON_ERROR_STOP=1 as postgres, one transaction.
-- Idempotent: a second run finds the original state and changes nothing.
--
-- Postflight (read-only): must return zero rows.
--   SELECT 'shortcut_tokens still exists' WHERE to_regclass('public.shortcut_tokens') IS NOT NULL
--   UNION ALL
--   SELECT 'capture key index still exists' WHERE to_regclass('public.uq_finva_candidates_capture_key') IS NOT NULL
--   UNION ALL
--   SELECT 'email_message_id nullable' FROM information_schema.columns
--   WHERE table_schema = 'public' AND table_name = 'finva_email_candidates' AND column_name = 'email_message_id'
--     AND is_nullable = 'YES';

BEGIN;

DO $rollback$
BEGIN
    IF EXISTS (SELECT 1 FROM public.finva_email_candidates WHERE email_message_id IS NULL) THEN
        RAISE EXCEPTION 'candidates without an email exist (captured by Shortcuts): decide them first';
    END IF;
END
$rollback$;

DROP INDEX IF EXISTS public.uq_finva_candidates_capture_key;
DROP TABLE IF EXISTS public.shortcut_tokens;
ALTER TABLE public.finva_email_candidates ALTER COLUMN email_message_id SET NOT NULL;

COMMIT;
