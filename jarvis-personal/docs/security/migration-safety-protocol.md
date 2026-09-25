# DINCR migration safety, backups and destructive SQL

Rules for every change to the production database: migrations, manual SQL, restores. It complements `CLAUDE.md` §3 (merge = possible deploy) and §6 (human gates).

**Why this exists.** One class of error this document prevents is a *legacy identity namespace collision during administrative maintenance*:
- a hand-written cleanup selects rows by a legacy integer identifier;
- that integer denotes different people in different tables;
- rows of unrelated users are deleted;
- without a verified backup, they cannot be recovered.

Every rule below breaks one link of that chain: ad-hoc destructive SQL, selection by legacy ids, and a missing backup.

## 1. The BACKUP_VERIFIED gate

**No production migration, manual `UPDATE`/`DELETE`, bulk import or restore runs without a verified backup taken less than 6 hours earlier.**

A backup counts as verified only when it has been **restored** and the restored data matches. A dump file alone proves nothing.

```bash
# 1. Take the backup and prove it restores.
export DINCR_BACKUP_SOURCE_DSN=...   # direct (session) connection; never commit or paste it
export DINCR_BACKUP_SCRATCH_DSN=...  # an EMPTY scratch database (see below)
python backend/scripts/db_backup_verify.py backup --out ~/DINCR-backups

# 2. Check the gate (exit 0 only when open).
python backend/scripts/db_backup_verify.py gate --out ~/DINCR-backups --max-age-hours 6
```

**The scratch database** must be empty, and it must already have what the dumped schemas depend on:
- **Roles:** the Supabase roles referenced by policies and grants: `anon`, `authenticated`, `service_role`.
- **Schemas and extensions:** the `extensions` schema and the extensions used by column defaults.

A plain local PostgreSQL works once they exist:
```sql
CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;
CREATE SCHEMA extensions; CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA extensions;
```

**Dependencies and failure:**
- Public tables that reference `auth.users` also need a stub `auth.users (id uuid primary key)`.
- If anything is missing, the restore reports FAILED and the gate stays closed. **Never widen the tolerated restore errors to make a backup pass.**

**The `auth` schema:**
- By default only `public` is backed up.
- Backing up `auth` (`--schema auth`) copies sessions, refresh tokens and MFA secrets. Do it only onto encrypted storage you control.
- `auth` cannot be restored into a Supabase stack whose `auth` tables already exist.

**The first real drill** against production data is a human action. Record its result, including any preparation the scratch database needed.

**What the tool does:**
- It dumps inside one exported snapshot, with owners, GRANT/REVOKE and default privileges, and counts every table in that same snapshot.
- It records the source's fingerprint (database, server address and port) and its table list.
- It restores into the empty scratch database and compares the counts table by table.
- It writes `manifest.json` with the dump's SHA-256.
- The gate prints `BACKUP_VERIFIED <stamp> database=… tables=… rows=… sha256=…` only when the newest backup is VERIFIED, young enough (at most 24 h) and unmodified. A backup of zero tables never verifies.
- Connection strings reach `pg_dump`/`pg_restore` through environment variables, never through a command line.

**Where backups live:**
- The output directory must be outside any Git repository; the tool refuses otherwise.
- The directory is 0700 and files are 0600.
- Dumps hold personal financial data. Keep them encrypted at rest, off shared drives, and delete them on the retention schedule (§4).

**What to record:** paste the `BACKUP_VERIFIED …` line into the PR or change record. It contains no connection data.

## 2. Applying a migration

1. **Merged first.** The migration is reviewed and merged on `main`, and its PR states the PRE-MERGE GATE (`CLAUDE.md` §3).
2. **Preflight.** Run the migration's preflight (read-only) and keep the output.
3. **Backup.** The BACKUP_VERIFIED gate is open (§1).
4. **Apply through the tool, never by pasting SQL into an editor:**
   ```bash
   git fetch origin
   export DINCR_MIGRATION_DSN=...    # direct session connection
   python backend/scripts/apply_migration.py \
       --file database/migrations/<name>.sql --backup-dir ~/DINCR-backups \
       --confirm <name>.sql
   ```
   The tool refuses to run when:
   - the file is not byte-identical to `origin/main` (fetched at run time);
   - it is not exactly one transaction (`BEGIN` first, `COMMIT` last, no other transaction control, nothing after `COMMIT`);
   - the backup gate is closed;
   - the target is a different database than the backup's source, or its tables differ from the backup's;
   - the same file was already applied to that database (ledger `applied.jsonl` in the backup directory);
   - `--confirm` does not repeat the file name.

   **How it runs:**
   - The session is named `dincr-migration` and has a default 5 s `lock_timeout`.
   - An error rolls back the whole transaction and prints only its SQLSTATE.
   - A transaction left open is rolled back and reported as FAILED.
   - **Verification queries** belong in the postflight, not after `COMMIT`.

5. **Postflight.** Run the migration's postflight. Any failing row means stop, investigate, and use the migration's rollback file if it has one.
   - **Rollback files** live in `database/rollback/`, so `apply_migration.py` refuses them by design. They are the one allowed exception to §3:
     - the BACKUP_VERIFIED gate is open for the same database;
     - a second person has read the file and agreed with the reason;
     - it runs with `psql -v ON_ERROR_STOP=1` over a direct session connection, as the owner role, in the file's single transaction.
6. **Quiet window.** Migrations set their own `lock_timeout`. If it fires, nothing was applied; retry later.

## 3. Destructive SQL policy

Ad-hoc destructive SQL against production (`DELETE`, `UPDATE` of financial rows, `TRUNCATE`, `DROP`) is **prohibited** in the SQL editor, in psql, and in scripts that did not go through review. The only allowed forms are:

- **The app's own account-deletion flow**, for a user deleting their account.
- **A reviewed, merged migration** applied with `apply_migration.py`.
- **A reviewed maintenance script** in `backend/scripts/`, run after the backup gate, when both of these hold:
  - it scopes every statement to one workspace;
  - it passes the same review as code.

**Any destructive statement, however it is run, must follow these rules:**
- **Never select rows by a legacy integer identifier** (`user_id`, `allowed_users.id`, `users.id`). The same integer denotes different people in different tables. Select by `workspace_id` and primary key only.
- **One workspace per statement.** Where the ownership guard is installed, declare it first: `SET LOCAL dincr.delete_workspace = '<workspace uuid>'`. Rows without a workspace take the explicit declaration `'none'`, and are deleted in their own statement.
- **Never loop over the catalog.** A `DO` block that deletes from "every table with column X" is forbidden: new tables silently join the blast radius.
- **Preview in the same transaction.** Count the rows first. The delete uses `RETURNING`, and its count must equal the preview, or you `ROLLBACK`.
- **Two people.** A second person reads the exact statement and the preview output before `COMMIT`.
- **No `TRUNCATE`** of any table holding user data.

**Template:**

```sql
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL dincr.delete_workspace = '<workspace uuid>';
SELECT count(*) FROM <table> WHERE workspace_id = '<workspace uuid>' AND id = ANY('{…}'::bigint[]);
DELETE FROM <table> WHERE workspace_id = '<workspace uuid>' AND id = ANY('{…}'::bigint[]) RETURNING id;
-- The RETURNING count must equal the preview. Otherwise: ROLLBACK;
COMMIT;
```

## 4. Backup and disaster-recovery architecture

**Know your plan's coverage:**
- Check whether the production project includes platform backups and point-in-time recovery.
- Without either, and without §1, a deleted row cannot be recovered, so the recovery point objective (RPO) is unbounded.
- Record the current coverage in the private operations record, not here.

**Options for a human decision.** No plan change has been made.

| Option | RPO | Effort | Notes |
|---|---|---|---|
| A. Scheduled logical backups with `db_backup_verify.py` (daily, stored encrypted off-platform) | 24 h | low | Works on any plan. The restore is proven on every run. Storage and retention are ours to manage. |
| B. Paid plan with daily platform backups | 24 h | none | Restores the whole project, and restore granularity is the platform's. Keep A for verified exports. |
| C. B plus point-in-time recovery | minutes | none | The only option that bounds loss to minutes. |

**Recommendation: A now, then C before a wider launch.**
- **Retention:** 7 daily and 4 weekly backups, deleted after that.
- **Restore drill (quarterly and after any schema-heavy release):**
  1. Restore the newest backup into a scratch environment.
  2. Run the app's read smoke tests against it.
  3. Record the time taken (RTO) and any restore errors in the release notes.

  A drill that was not run counts as failed.

**Not covered by a database dump:** Storage objects, Auth configuration, Edge Function code and secrets. Each needs its own export or must be reproducible from the repository.

## 5. Checklist (copy into the change record)

- [ ] Migration merged; its PR lists the PRE-MERGE GATE
- [ ] Preflight output reviewed
- [ ] `BACKUP_VERIFIED …` line recorded (< 6 h old)
- [ ] Applied with `apply_migration.py`
- [ ] Postflight: zero failing rows
- [ ] No ad-hoc destructive SQL was run, or it followed §3 with a second reviewer
