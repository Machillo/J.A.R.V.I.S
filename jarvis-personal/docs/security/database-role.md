# Application database role (`dincr_app`)

The backend connects to Postgres as the privileged table owner. Any bug or injection in a request path therefore runs with full rights:
- DDL;
- every table;
- Vault;
- bypassing row level security.

This document covers:
- the dedicated role that replaces that connection;
- how to switch to it;
- how row level security is tightened after the switch.

## What the role can do

Migrations, in order:

| Migration | What it does |
|---|---|
| `20260926125000_owner_legacy_schema` | Moves the last runtime DDL into a migration. The code runs no DDL (`test_no_runtime_ddl.py`). |
| `20260926149000_mail_secret_boundary` | `dincr_private.mail_secret_create/read/delete`: SECURITY DEFINER, `search_path = pg_catalog, pg_temp`, no EXECUTE for PUBLIC/anon/authenticated. They handle only DINCR mail tokens whose description names the given account. |
| `20260926150000_dincr_app_role` | Creates the role, grants, policies, and the transitional delete guard. |
| `20260926151000_guard_by_app_role` | After the switch, the delete guard trusts only `session_user = 'dincr_app'`. |

`dincr_app` has:
- **Attributes:** `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT`, and no role memberships. `idle_in_transaction_session_timeout = 60s`.
- **Ownership:** nothing, and no CREATE on any schema. The migration aborts (`APP01`) if PUBLIC would give it CREATE on `public`.
- **Table privileges:** explicit per table (SELECT/INSERT/UPDATE/DELETE), derived from the SQL the backend runs. `backend/tests/test_dincr_app_grants.py` fails when code needs a privilege no migration grants, and when a grant is no longer used.
- **Sequences:** USAGE (nextval) only on those owned by tables it inserts into. No setval.
- **Catalog-derived grants:**
  - DELETE on every table with a foreign key to `allowed_users`, because account deletion deletes from them dynamically;
  - SELECT on every table with `account_id` or `workspace_id`, because the personal-data export reads them all and must never silently skip one.
- **Row level security:** stays on for every table the role can reach, with one explicit policy each: `dincr_app_access`, `USING (true)`. Without it the role would silently read no rows. The strict phase below replaces it.
- **Schemas:** no USAGE on `vault`, `auth` or `storage`. Mail tokens go only through `dincr_private`.
- **Functions:** EXECUTE on the three `dincr_private` mail functions only. They are STRICT: a NULL account does nothing.
- **Migrator:** everything is created by a non-superuser migrator with CREATEROLE/CREATEDB, like Supabase's `postgres`. Superuser-only attributes are verified (`APP01`), not altered. The rollback revokes explicitly instead of `DROP OWNED BY`. `backend/tests/test_dincr_app_role_pg.py` runs as such a migrator (Postgres 16).

**What the role does not protect against.** A compromised `dincr_app` can still:
- read every connection's `(secret id, account)` pair and so every mail token, through the boundary;
- read and write every granted table.

It cannot:
- run DDL;
- read other Vault secrets, `auth` or `storage`;
- disable the triggers;
- delete financial rows across owners.

Strict RLS (below) narrows the table access.

The #245 delete guard used to recognise "the application" by `application_name`, which any client sets freely. It now uses the login role, which a client cannot fake. Every other login must `SET LOCAL dincr.delete_workspace`.

## Switching the backend to `dincr_app` (HUMAN-ONLY)

The production DSN, the password and the Render and Supabase settings are human steps. Nothing in the repository contains them.

1. **Before anything,** apply `20260926125000` (from the runtime-DDL PR), then `20260926149000` and `20260926150000`, with `backend/scripts/apply_migration.py` (BACKUP_VERIFIED). Each postflight must return 0 rows.
2. **Deploy** the code that uses `dincr_private`, with the runtime DDL removed. The backend still connects as before and keeps working, because the guard accepts both identities.
3. **Set the password** in the Supabase SQL editor, never in a file or chat:
   ```sql
   ALTER ROLE dincr_app PASSWORD '<generated, 32+ random characters>';
   ```
4. **Check database-level settings** that every role could read, listing names only and never values:
   - `SELECT setdatabase, setrole, array_length(setconfig, 1) FROM pg_db_role_setting;`
   - `SELECT name FROM pg_settings WHERE name LIKE 'app.%';`

   A readable JWT or service secret there would undo this work.

5. **Build the pooler connection string** for the role. The Supavisor transaction-mode user is `dincr_app.<project-ref>`, with the same host and port as today. Put it in Render as the backend's `DATABASE_URL` for the web service and every worker or cron. Keep the migration runner's DSN on the owner role; migrations need DDL.
6. **Verify** after the redeploy:
   - `SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1, 2;` shows the backend's sessions as `dincr_app`.
   - The log shows no `permission denied`.
   - The Owner and a User account can:
     - log in;
     - open Home, Debts and Movements;
     - connect and disconnect a mailbox;
     - export data;
     - delete a test account.
7. **Only then** apply `20260926151000` (PRE-APPLY GATE: step 6 done). Postflight: 0 rows.

After that, any session using the application's connection string is "the application" for the delete guard. Keep that password in Render only. Operator scripts use the owner connection string and declare `dincr.delete_workspace`.

**Rollback of the switch:**
1. Put the previous `DATABASE_URL` back in Render.
2. If `20260926151000` was applied, roll it back first (`database/rollback/20260926151000_…`); otherwise the old connection's deletes are refused.
3. Rolling back the role itself (`database/rollback/20260926150000_…`) is only needed to remove it.

## Strict row level security (next phase, separate change)

The `dincr_app_access` policies are `USING (true)`: tenancy is still enforced by the application (`account_id`/`workspace_id` predicates on every query). The strict phase makes Postgres enforce it too.

### Design

- **Context:** the workspace is passed per transaction with `set_config('dincr.workspace_id', '<uuid>', true)`.
  - `is_local = true` makes it transaction-scoped. That is required with Supavisor in transaction mode: a server connection is shared between clients across transactions, so session-level settings would leak from one request to another.
  - `backend/core/database.get_connection()` sets it at the start of each transaction, from the authenticated request context. Background jobs set it per job, from the row they process.
- **Missing context is an error, never an empty result.** In finance, an empty result reads as "no debts" or "no income", and unknown is not zero. Policies call `dincr_private.current_workspace()`, which raises `42501` when the setting is missing or not a UUID. So a transaction without context fails; it never shows zero, and it never falls back to the Owner.
  ```sql
  USING (workspace_id = dincr_private.current_workspace())
  WITH CHECK (the same)
  ```
- **Cross-workspace paths are not unlocked by a setting.** The application role can set any setting itself, so a setting would be no protection against an injection. These paths use SECURITY DEFINER functions with their own checks, or run under a separate role with its own credentials, never `dincr_app`:
  - account deletion;
  - crons that fan out across workspaces (mail maintenance, notifications, store lapses);
  - Owner administration;
  - identity resolution at login.

  The strict-RLS change carries a guard test listing them.
- **Identity tables:** `accounts`, `workspaces`, `workspace_members` and `allowed_users` are read at login, before a workspace is known, through a SECURITY DEFINER lookup keyed by the verified Supabase user id. The login path gets no ambient read.
- **Guard test:** every table the role can reach must have a `dincr_app` policy, so a new table can never be silently empty. The role migration's postflight already checks this for `dincr_app_access`.
- **Rollout:**
  1. Ship the context setting in `get_connection()`, with a test that every transaction sets it.
  2. Add the strict policies next to `dincr_app_access` as `RESTRICTIVE`, table by table, and watch for `42501`.
  3. Drop `dincr_app_access`.

  Each step is a reviewed migration with a rollback.

## Out of scope here

- Moving `anon`/`authenticated` (PostgREST) further: they already have no table grants.
- Supabase Auth settings and pool sizing (see the load-test report).
