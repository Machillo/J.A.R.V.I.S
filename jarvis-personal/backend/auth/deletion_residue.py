"""What account deletion must leave behind: nothing that points at the person.

``residue_report`` looks for a deleted account's identifiers anywhere in the
``public`` schema, whatever the table's FKs, and reports table, column and a
count, never row contents. It is read-only. The deletion tests and
backend/scripts/verify_account_deletion.py use it after a real deletion.

What it scans:
- every ``uuid`` and ``uuid[]`` column, for the account id and the workspace ids;
- every text column, for those ids written as text (for example a repair log);
- when given, the account email (normalized) in text columns.

Legacy integer ids (users.id, allowed_users.id) are deliberately not searched:
the same integer names different people in different tables (the 2026-09-17
incident), so a match would report someone else's rows as residue. Legacy rows
are removed by the deletion flow through their FKs, never selected by integer.

What it cannot see (checked elsewhere, listed in NOT_SCANNED): Supabase-managed
schemas (auth, including auth.audit_log_entries; storage), Vault, backups and
logs outside the database, and third parties (PostHog, support mailbox, Render).

Deliberate retention (documented, never personal content):
- financial_ownership_delete_log: the security audit of financial deletes (#245).
  It keeps opaque ids of rows and live workspaces deleted before the account was,
  so a data-loss incident can be investigated. No names, amounts or descriptions.
- store_subscription_events: kept with account_id nulled by its FK. Provider event
  ids, plan and period stay for store idempotency and refunds.
"""
from __future__ import annotations

from typing import Iterable

RETAINED = frozenset({("financial_ownership_delete_log", "workspace_ids")})
NOT_SCANNED = (
    "legacy integer ids (ambiguous across id spaces; removed through their FKs)",
    "Supabase schemas (auth, including auth.audit_log_entries; storage)",
    "Vault secrets",
    "database backups and platform logs",
    "third parties (PostHog, support mailbox, Discord, Render)",
)


def _columns(conn) -> list[dict]:
    # pg_catalog, not information_schema: the latter hides columns the role cannot read,
    # which would turn a missing privilege into a silent "no residue".
    return conn.execute(
        """SELECT c.relname AS table_name, a.attname AS column_name, t.typname AS type_name
           FROM pg_catalog.pg_attribute a
           JOIN pg_catalog.pg_class c ON c.oid = a.attrelid AND c.relkind IN ('r', 'p')
           JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
           JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
           WHERE a.attnum > 0 AND NOT a.attisdropped
             AND t.typname IN ('uuid', '_uuid', 'text', 'varchar')
           ORDER BY c.relname, a.attname"""
    ).fetchall()


def residue_report(conn, account_id: str, workspace_ids: Iterable[str], *, email: str | None = None) -> list[dict]:
    ids = [str(account_id), *(str(w) for w in workspace_ids)]
    normalized_email = (email or "").strip().lower() or None
    found = []
    for column in _columns(conn):
        table, name, kind = column["table_name"], column["column_name"], column["type_name"]
        if (table, name) in RETAINED:
            continue
        col = _quote(name)
        checks = []
        if kind == "uuid":
            checks.append((f"{col} = ANY(%s::uuid[])", ids))
        elif kind == "_uuid":
            checks.append((f"{col} && %s::uuid[]", ids))
        elif kind in {"text", "varchar"}:
            checks.append((f"{col} = ANY(%s::text[])", ids))
            if normalized_email:
                checks.append((f"lower(btrim({col})) = %s", normalized_email))
        for predicate, value in checks:
            # Identifiers come from the catalog and are quoted; the values are parameters.
            row = conn.execute(f"SELECT count(*) AS n FROM public.{_quote(table)} WHERE {predicate}", (value,)).fetchone()
            count = int((row or {}).get("n") or 0)
            if count:
                found.append({"table": table, "column": name, "rows": count})
    return found


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
