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
- **Row level security:** stays on everywhere, with one explicit policy per granted table: `dincr_app_access`, `USING (true)`. The strict phase below replaces it.
- **Schemas:** no USAGE on `vault`, `auth` or `storage`. Mail tokens go only through `dincr_private`.
- **Functions:** EXECUTE on the three `dincr_private` mail functions only.

The #245 delete guard used to recognise "the application" by `application_name`, which any client sets freely. It now uses the login role, which a client cannot fake. Every other login must `SET LOCAL dincr.delete_workspace`.

## Switching the backend to `dincr_app` (HUMAN-ONLY)

The production DSN, the password and the Render and Supabase settings are human steps. Nothing in the repository contains them.

1. **Before anything,** apply `20260926125000` (from the runtime-DDL PR), then `20260926149000` and `20260926150000`, with `backend/scripts/apply_migration.py` (BACKUP_VERIFIED). Each postflight must return 0 rows.
2. **Deploy** the code that uses `dincr_private`, with the runtime DDL removed. The backend still connects as before and keeps working, because the guard accepts both identities.
3. **Set the password** in the Supabase SQL editor, never in a file or chat:
   ```sql
   ALTER ROLE dincr_app PASSWORD '<generated, 32+ random characters>';
   ```
4. **Build the pooler connection string** for the role. The Supavisor transaction-mode user is `dincr_app.<project-ref>`, with the same host and port as today. Put it in Render as the backend's `DATABASE_URL` for the web service and every worker or cron. Keep the migration runner's DSN on the owner role; migrations need DDL.
5. **Verify** after the redeploy:
   - `SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1, 2;` shows the backend's sessions as `dincr_app`.
   - The log shows no `permission denied`.
   - The Owner and a User account can:
     - log in;
     - open Home, Debts and Movements;
     - connect and disconnect a mailbox;
     - export data;
     - delete a test account.
6. **Only then** apply `20260926151000` (PRE-APPLY GATE: step 5 done). Postflight: 0 rows.

**Rollback of the switch:**
1. Put the previous `DATABASE_URL` back in Render.
2. If `20260926151000` was applied, roll it back first (`database/rollback/20260926151000_…`); otherwise the old connection's deletes are refused.
3. Rolling back the role itself (`database/rollback/20260926150000_…`) is only needed to remove it.

## Strict row level security (next phase, separate change)

The `dincr_app_access` policies are `USING (true)`: tenancy is still enforced by the application (`account_id`/`workspace_id` predicates on every query). The strict phase makes Postgres enforce it too.

### Design

- **Context:** the workspace is passed per transaction with `set_config('dincr.workspace_id', '<uuid>', true)`.
  - `is_local = true` makes it transaction-scoped. That is required with Supavisor in transaction mode: a server connection is shared between clients across transactions, so session-level settings (`SET`, `is_local = false`) would leak from one request to another.
  - `backend/core/database.get_connection()` sets it at the start of each transaction, from the authenticated request context. Background jobs set it per job, from the row they process.
- **Policies:** each workspace-owned table gets:
  ```sql
  USING (workspace_id = NULLIF(current_setting('dincr.workspace_id', true), '')::uuid)
  WITH CHECK (the same)
  ```
  A transaction without context sees no rows and cannot write: it fails closed. It never falls back to the Owner.
- **Cross-workspace paths** are explicit, never an ambient bypass:
  - account deletion;
  - crons that fan out across workspaces (mail maintenance, notifications);
  - Owner administration;
  - identity resolution at login.

  They use SECURITY DEFINER functions with their own checks, or run as a separate role whose policies allow a declared scope (`dincr.scope = 'system'`), set with `is_local = true` and only in those code paths. The strict-RLS change carries a guard test listing them.
- **Identity tables:** `accounts`, `workspaces`, `workspace_members` and `allowed_users` are read before a workspace is known, at login. Their policies key on the Supabase user id (`dincr.auth_user_id`, transaction-local) instead of the workspace.
- **Rollout:**
  1. Ship the context setting in `get_connection()`, with a test that every transaction sets it.
  2. Add the strict policies next to `dincr_app_access` as `RESTRICTIVE`, table by table, and watch for denials.
  3. Drop `dincr_app_access`.

  Each step is a reviewed migration with a rollback. Denials surface as empty results or `42501`, never as wrong data.

## Out of scope here

- Moving `anon`/`authenticated` (PostgREST) further: they already have no table grants.
- Supabase Auth settings and pool sizing (see the load-test report).
