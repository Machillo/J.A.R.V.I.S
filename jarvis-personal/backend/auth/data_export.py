"""Self-service copy of the authenticated account's data (privacy right of access).

Tables are discovered from the catalog: every public table with an
``account_id`` or ``workspace_id`` column is exported, filtered to the caller's
account and the workspaces it owns. New features are therefore included
without touching this module. Credentials and internal secrets are never
exported.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from backend.auth.current_user import get_current_account_id
from backend.core.database import get_connection


EXPORT_FORMAT_VERSION = 1
MAX_ROWS_PER_TABLE = 20000
# Columns that reference secrets or internal infrastructure, not user data.
EXCLUDED_COLUMNS = {"refresh_token_secret_id", "history_id", "watch_expiration", "initial_scan_page_token"}
EXCLUDED_TABLES = {"accounts", "workspaces"}
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _quote(identifier: str) -> str:
    if not _IDENTIFIER.match(identifier):
        raise ValueError(f"Unexpected identifier {identifier!r}")
    return f'"{identifier}"'


def _owned_tables(conn) -> dict[str, list[str]]:
    rows = conn.execute(
        """SELECT c.table_name, c.column_name
           FROM information_schema.columns c
           JOIN information_schema.tables t
             ON t.table_schema=c.table_schema AND t.table_name=c.table_name
           WHERE c.table_schema='public' AND t.table_type='BASE TABLE'
           ORDER BY c.table_name, c.ordinal_position"""
    ).fetchall()
    tables: dict[str, list[str]] = {}
    for row in rows:
        tables.setdefault(row["table_name"], []).append(row["column_name"])
    return {
        name: columns for name, columns in tables.items()
        if name not in EXCLUDED_TABLES and ({"account_id", "workspace_id"} & set(columns))
    }


def export_current_account_data() -> dict:
    account_id = get_current_account_id()
    with get_connection() as conn:
        account = conn.execute(
            """SELECT id, primary_email, display_name, created_at FROM accounts WHERE id=%s""",
            (account_id,),
        ).fetchone()
        workspaces = conn.execute(
            "SELECT id, name, workspace_type, created_at FROM workspaces WHERE owner_account_id=%s",
            (account_id,),
        ).fetchall()
        workspace_ids = [str(row["id"]) for row in workspaces]

        data: dict[str, list[dict]] = {}
        truncated: list[str] = []
        for table, columns in sorted(_owned_tables(conn).items()):
            selected = [column for column in columns if column not in EXCLUDED_COLUMNS]
            filters, params = [], []
            if "account_id" in columns:
                filters.append("account_id::text=%s")
                params.append(account_id)
            if "workspace_id" in columns and workspace_ids:
                filters.append("workspace_id::text = ANY(%s)")
                params.append(workspace_ids)
            if not filters:
                continue
            rows = conn.execute(
                f"SELECT {', '.join(_quote(column) for column in selected)} FROM {_quote(table)} "
                f"WHERE {' OR '.join(filters)} LIMIT %s",
                (*params, MAX_ROWS_PER_TABLE + 1),
            ).fetchall()
            if len(rows) > MAX_ROWS_PER_TABLE:
                rows = rows[:MAX_ROWS_PER_TABLE]
                truncated.append(table)
            if rows:
                data[table] = rows
        conn.rollback()

    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "workspaces": workspaces,
        "data": data,
        "truncated_tables": truncated,
        "notes": "Copia de los datos asociados a tu cuenta DINCR. Las autorizaciones de correo y otros secretos no se incluyen.",
    }
