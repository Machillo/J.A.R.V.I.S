# Canonical identity migration (legacy user_id retirement)

Status: plan. Phase A is prepared by the financial ownership integrity migration
(`database/migrations/20260925120000_financial_ownership_integrity.sql`), which
has not been applied. Every later phase needs its own reviewed PR, and a human
gate for any migration.

## Target

```
Supabase Auth user (UUID)
  └─ accounts.id            (accounts.supabase_user_id, UNIQUE)
       └─ workspaces.id     (owner_account_id; members in workspace_members)
            └─ financial rows (workspace_id NOT NULL; account_id where the actor matters)
```

- `workspace_id` is the only ownership key of financial data.
- `account_id` records **who acted** (audit or attribution). It never decides ownership.
- `allowed_users` and `users` become legacy bridges, and are then retired.

## Why the legacy user_id must stop meaning anything

The financial `user_id` column has **two id spaces** with the same integer
range:

| Writer | Value written |
|---|---|
| Owner/Personal services, email monitor, overtime, the `DEFAULT 1` | `allowed_users.id` |
| DINCR Users services (`_legacy_financial_user_id`), mail candidates, statement discovery | `users.id` of the account email |

Real data contains collisions: one account's `users.id` equals another account's
`allowed_users.id`. A bare integer cannot say which space it came from, so
nothing may decide ownership with it.
- No financial read is scoped by `user_id`: every read and write filters by `workspace_id`.
- `test_no_backend_query_decides_by_legacy_user_id` scans every SQL literal for a comparison on `user_id`, on either side of any operator.
- The only comparisons left are three notification joins to `allowed_users`, on tables written only with `allowed_users.id`. They are allowlisted, and removing them is part of Phase C.

A second risk class exists: when a table's `user_id` FK points at one space
and a writer stores a value from the other, **deleting an unrelated person** in
that space cascades to the row.
- E10 confirmed the production FKs.
- Phase A therefore checks each table in the space its FK references, and flags existing wrong-space rows as `USER_ID_WRONG_SPACE`.
- With every row in its FK's space, a cascade only removes the deleted person's own rows.

## Deletions by legacy id (class of error)

A cleanup that selects financial rows by a legacy integer, for example `WHERE workspace_id = ANY(targets) OR user_id = ANY(<the targets' allowed_users.id>)`, also matches **other people's** rows in tables whose `user_id` references `users(id)`, in every workspace.

Phase A:
- rejects any financial DELETE touching live workspaces of more than one owner;
- requires every session other than the application's pooler connection (`application_name = 'Supavisor'`; the SQL editor, psql, scripts, the CLI and agents) to declare the one workspace it deletes from (`SET LOCAL dincr.delete_workspace = '<uuid>'`, never a session-level `SET`);
- rejects TRUNCATE of financial tables;
- blocks deleting a legacy identity whose FK would cascade into another workspace;
- logs every committed financial deletion (identifiers of live workspaces only; deletions from removed workspaces keep a count).

Limits:
- A privileged role can disable triggers or change `application_name`.
- A human or script connecting through the same pooler also reports `Supavisor` and is treated as the app. Only the one-owner check and the delete log apply there.
- The rule below and the delete log are the safeguards in both cases.
- If workspace sharing ships, account deletion must first remove the member's rows in other owners' workspaces. Otherwise the identity guard fails that deletion closed.

Rule for humans and agents: **never delete or select financial rows by legacy `user_id`.** Remove an account through the account deletion flow; it deletes the account and its workspaces cascade.

## Inventory (backend, excluding tests)

| Dependency | Where | Class |
|---|---|---|
| `allowed_users` as login gate, status and deletion tombstone | `auth/service.py` (`authenticate_access_token`, `delete_current_account`, `_replace_stale_deletion_tombstone`) | CURRENT REQUIRED |
| Workspace resolved from `accounts.legacy_allowed_user_id` | `auth/workspace_context.py::resolve_personal_workspace_context`, `sync_account_auth_identity` | CURRENT REQUIRED → SAFE TO MIGRATE (resolve by `accounts.supabase_user_id`) |
| Per-person tables keyed by `allowed_users(id)` via FK: settings, memory, chat, preferences, advisor, `financial_input_events`, `notification_jobs` | `ai/*`, `advisor/core.py`, `notifications/service.py`, `user_product/gmail_service.py` | CURRENT REQUIRED (FK) → SAFE TO MIGRATE to `account_id` |
| `users.id` bridge for legacy finance FKs | `user_product/service.py::_legacy_financial_user_id`, `gmail_service._financial_user_id_for_account`, `mail_oauth.py`, `microsoft_mail.py`, `financial_identity.py`, `finva_gmail_connections.legacy_user_id` (FK → users) | LEGACY COMPATIBILITY |
| Financial `user_id` written by every financial writer (`get_current_user_id()` in about 25 modules; users bridge in DINCR) | `finance/*`, `goals`, `transactions`, `core/events`, `user_product/*`, `email_monitor/*` | LEGACY COMPATIBILITY (value only; no financial read filters by it) |
| Notification joins `allowed_users.id = <table>.user_id` (`notification_subscriptions`, `events`, `fixed_expenses`) | `notifications/service.py` | LEGACY COMPATIBILITY; correct only while those tables are written with `allowed_users.id` → Phase C |
| Deletion of rows by `allowed_users.id` on every FK to `allowed_users` | `auth/service.py::_delete_allowed_user_dependents`, plus the FK cascade when the tombstone is deleted | NEEDS REVIEW. If any dual-space table references `allowed_users`, deleting one account removes another tenant's colliding rows (E10) → Phase E removes those FKs |
| `DEFAULT 1` on legacy `user_id` columns (Owner fallback) | database | LEGACY. It is dangerous: the Phase A trigger rejects it outside the Owner workspace |
| Id-space mixing: `notifications/service.py::_display_name` (`users` looked up with an `allowed_users.id`, hardcoded fallback name), `integrations/ibkr_readonly.py::_owner_identity` (`users.id = legacy_allowed_user_id` join), dead `email_monitor::_owner_user_id` | as listed | UNKNOWN / NEEDS REVIEW (fix before Phase B) |
| Production FKs (E10): `debts`, `expenses`, `financial_goals`, `investments`, `savings`, `transactions` → `users(id)` ON DELETE CASCADE; `fixed_expenses`, `fixed_expense_matches`, `financial_input_events`, `notification_jobs` → `allowed_users(id)` CASCADE | database | CURRENT REQUIRED (the FK decides the space of each table) → retired in Phase E |
| FK of `payroll_events.user_id`, which is written with `allowed_users.id` by overtime | database | UNKNOWN: if it references `users`, overtime rows attach to another person |

## Phases

**Phase A: immediate protection.**
- Read-only audit, preflight, forensic queries and a release-gate script.
- Safe repair only for the SAFE_AUTO_FIX class.
- New writes must carry a workspace, and children must match their parent's workspace.
- Existing rows are never moved between workspaces by application writes.
- A changed legacy `user_id` must be an identity of the workspace in the space its table's FK references (either space when the table has no such FK). NULL is accepted.
- A colliding id is never used to repair a row.
- Deletions: one owner per statement, declared workspace for manual sessions, no TRUNCATE, no cross-workspace cascades from `users`/`allowed_users`, and a delete log.
- Tested rollback.
- Exit: preflight reviewed, every NEEDS_REVIEW/ORPHAN row resolved by a human, migration applied, check script PASS.

**Phase B: writers use only the canonical identity.**
- Add `account_id UUID NULL REFERENCES accounts(id) ON DELETE SET NULL` (actor) to financial tables where attribution is useful.
- Every writer sets `workspace_id` from the session and `account_id` from the session.
- Writers keep filling the legacy `user_id` only because of NOT NULL and FKs, through a single helper per id space, so no call site chooses a space.
- Resolve the session by `accounts.supabase_user_id` rather than `legacy_allowed_user_id`.
- Fix the NEEDS REVIEW items of the inventory.
- Exit: static guard, meaning no financial INSERT without `workspace_id` + `account_id`.

**Phase C: readers use only workspace and account.**
- Already true for financial reads (guarded).
- Extend the guard to per-person tables: move settings, memory and advisor from `allowed_users(id)` to `account_id`, with dual-read during the switch.
- Exit: no reader uses `allowed_users.id` or `users.id` except the login bridge.

**Phase D: verifiable backfill.**
- Backfill `account_id` on historical rows **only** from `workspace_id → owner_account_id` (single-owner personal workspaces), never from `user_id`.
- Log before and after values, like the Phase A repair log. Idempotent, with preflight and postflight counts.
- Shared workspaces (members) get `account_id` NULL. Unknown is not a guess.

**Phase E: retire the legacy user_id from logic.**
- Make financial `user_id` nullable and drop `DEFAULT 1` (the Phase A guard already accepts NULL).
- Writers stop filling it. Drop FKs from financial `user_id` to `users`/`allowed_users` so an unrelated deletion can never cascade.
- The Phase A trigger then reduces to the workspace and parent checks and can be dropped.

**Phase F: retire legacy tables and columns.**
- Only after Phases B–E have been in production for a full release cycle, and after a backup.
- Drop `users` and the financial `user_id` columns.
- Reduce `allowed_users` to nothing, once login and deletion use `accounts` alone and the tombstone moves to `accounts`.
- Destructive: separate human-approved migration.

## Invariants for every phase

- Ownership is never inferred from `user_id`.
- No row is reassigned without a logged, reversible, tested rule.
- Every migration is idempotent, aborts on an unexpected identity state, ships with preflight and postflight, and leaves NEEDS_REVIEW rows untouched.
