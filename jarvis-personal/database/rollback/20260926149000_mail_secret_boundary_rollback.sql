-- Rollback of 20260926149000: removes the mail secret boundary functions.
--
-- PRE-ROLLBACK GATE: the deployed code no longer calls dincr_private (revert the
-- code first) and 20260926150000 is rolled back (no role holds EXECUTE on them).
-- Vault secrets are untouched.
-- BACKUP_VERIFIED and a second reviewer, as for any migration.

BEGIN;

SET LOCAL lock_timeout = '5s';

DROP FUNCTION IF EXISTS dincr_private.mail_secret_delete(UUID[], UUID);
DROP FUNCTION IF EXISTS dincr_private.mail_secret_read(UUID, UUID);
DROP FUNCTION IF EXISTS dincr_private.mail_secret_create(TEXT, UUID, TEXT);
DROP FUNCTION IF EXISTS dincr_private.mail_secret_owned(TEXT, UUID);
DROP SCHEMA IF EXISTS dincr_private;

COMMIT;
