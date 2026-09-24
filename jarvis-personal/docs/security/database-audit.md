# Database audit (pre-release, code-based)

Method: read-only review of `database/` (schema, baseline, migrations) and the backend queries. **No production database was queried or changed.** Items marked **PROD CHECK** need a read-only query by a human. The RLS/grant review lives in `release-security-audit.md`.

## Fixed in code (this PR)

- **HIGH: account deletion left CCSS salary reports behind.**
  - `payroll_salary_reports` (salary, employer number, verification code, written by the VIP Gmail flow) has no FK to `workspaces`, so the account → workspace cascade never reached it.
  - `delete_current_account` now deletes the rows for the account's workspaces inside the same transaction, before the account is deleted. This is covered by a test.
- **HIGH: `ON CONFLICT (workspace_id, dedupe_key)` on `notification_jobs` could not match** the partial unique index that the collision-hardening migration left behind (`WHERE dedupe_key IS NOT NULL`).
  - The four upserts (notifications, sports) now carry the same predicate, which Postgres needs to infer a partial index.
  - The predicate also matches a full unique index, so this is safe either way.

## Prepared migration: HUMAN GATE (`database/migrations/20260924180000_release_db_integrity.sql`, not applied)

1. An FK from `payroll_salary_reports.workspace_id` to `workspaces` with `ON DELETE CASCADE`, added `NOT VALID`.
   - **PROD CHECK:** count orphans with the query in the file.
   - Deleting the orphans (rows of already-deleted accounts) is a separate, destructive, manual step. Run `VALIDATE` after it.
2. A unique index on `email_monitor_settings(workspace_id)`, which the Owner upserts rely on.
   - **PROD CHECK:** confirm there are no duplicate workspaces first.
3. Indexes for the Users Gmail history query (`finva_email_messages(workspace_id, account_id, received_at)`) and the unindexed FKs walked by the deletion cascade.

## Open findings: need a decision or a production check

- **MEDIUM: `transactions.transaction_date` may be `TEXT`** (`schema.sql`).
  - Several Basic/VIP reports cast it with `::date`, so one malformed row makes the whole report fail, and range indexes can't be used.
  - **PROD CHECK:** `information_schema.columns`. If it is TEXT, clean the data and migrate it to `DATE`.
- **MEDIUM: no `CHECK` constraints** on core financial tables (`transactions`, `expenses`, `debts`, `debt_payments`, `financial_goals`, `salaries`, receivables).
  - Proposed: non-negative amounts and closed type/status sets, added `NOT VALID` and then validated.
  - Needs DINCR Finance review of the allowed values.
- **MEDIUM: legacy `user_id` columns have `DEFAULT 1`** (probably the Owner) and `workspace_id` is still nullable in the legacy tables.
  - Every current read filters by `workspace_id`, so no cross-read was found.
  - Proposal: drop the defaults, and `SET NOT NULL` once `jarvis_workspace_backfill_audit()` reports 0 unmapped rows (**PROD CHECK**).
- **MEDIUM: `schema.sql` cannot build a fresh database** (UNIQUE constraints are declared before their columns exist). Regenerate it from production (`pg_dump --schema-only`) or mark it as non-authoritative, which matters for disaster recovery.
- **LOW:**
  - Basic, VIP and Free month views run one ledger query per month, up to ~60 queries per screen. A single `GROUP BY date_trunc('month', …)` would replace them.
  - `product_events` keeps `workspace_id` after deletion (it is pseudonymous).
  - The `ai_*` runtime usage tables have no workspace FK.
  - Some Owner-only tables have `workspace_id` without an FK.

## Production backup tables `audit_backup_*_20260908`

- They are listed by the Supabase advisor, and no migration, script or code in the repository creates them: they were made by hand. They probably copy goals and receivables rows.
- They have no FK or cascade, so **account deletion never removes their data**.
- **PROD CHECK:** columns, row counts and whether they contain rows of deleted accounts.
- **HUMAN GATE:** once confirmed unnecessary, archive them securely if required, then `DROP` them.
