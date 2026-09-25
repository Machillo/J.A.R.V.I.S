# DINCR migration safety, backups and destructive SQL

Rules for every change to the production database: migrations, manual SQL, restores. It complements `CLAUDE.md` §3 (merge = possible deploy) and §6 (human gates).

**Why this exists.** A class of incident this document prevents is a *legacy identity namespace collision during administrative maintenance*. A hand-written cleanup selected rows by a legacy integer identifier. The same integer meant different people in different tables, so rows of unrelated users were deleted. No backup existed, so the rows could not be recovered. Every rule below addresses one of those links: ad-hoc destructive SQL, selection by legacy ids, and the missing backup.

## 1. The BACKUP_VERIFIED gate

**No production migration, manual `UPDATE`/`DELETE`, bulk import or restore runs without a verified backup taken less than 6 hours earlier.**

A backup counts as verified only when it has been **restored** and the restored data matches. A dump file alone proves nothing.

```bash
# 1. Take the backup and prove it restores.
#    - Source: a direct (session) connection. Exported snapshots do not survive a transaction pooler.
#    - Scratch: an EMPTY database that has the same extensions and schemas the dumped
#      schemas depend on (for Supabase, a local `supabase start` stack or a
#      throwaway project, and include --schema auth if public tables reference it).
export DINCR_BACKUP_SOURCE_DSN=...   # never commit, never paste into tickets or chats
export DINCR_BACKUP_SCRATCH_DSN=...
python backend/scripts/db_backup_verify.py backup --out ~/DINCR-backups --schema public --schema auth

# 2. Check the gate (exit 0 only when open).
python backend/scripts/db_backup_verify.py gate --out ~/DINCR-backups --max-age-hours 6
```

**What the tool does:**
- It dumps inside one exported snapshot and counts every table in that same snapshot.
- It restores into the empty scratch database and compares the counts table by table.
- It writes `manifest.json` with the dump's SHA-256.
- The gate prints `BACKUP_VERIFIED <stamp> tables=… rows=… sha256=…` only when the newest backup is VERIFIED, young enough and unmodified.

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
   - the file is not byte-identical to `origin/main`;
   - it has no explicit `BEGIN; … COMMIT;`;
   - the backup gate is closed;
   - `--confirm` does not repeat the file name.

   The session is named `dincr-migration`. A failure rolls the whole file back.
5. **Postflight.** Run the migration's postflight. Any failing row means stop, investigate, and use the migration's rollback file if it has one.
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
- **One workspace per statement.** Where the ownership guard is installed, declare it first: `SET LOCAL dincr.delete_workspace = '<workspace uuid>'`.
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

**Current state:** the production project's plan includes no platform backups and no point-in-time recovery. Without §1, a deleted row is gone, so the recovery point objective (RPO) is unbounded.

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
