"""The application role (dincr_app) is granted exactly what the backend's SQL needs.

The backend connects as dincr_app, which has only explicit per-table privileges
(database/migrations/20260926150000_dincr_app_role.sql and later migrations). A
query on a table or with a command the role was not granted fails in production
with "permission denied". This test reads the SQL the runtime code runs and every
"GRANT ... ON TABLE public.<t> TO dincr_app" in the migrations, and fails when the
code needs more than is granted. A new table or command therefore ships with its
GRANT in the migration that introduces it.

Known limits (it is a guard, not a proof): SQL assembled from separate literals and
dynamic table names are not followed; the dynamic deletions of account deletion are
listed in DYNAMIC_DELETE.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND.parent / "database" / "migrations"

TABLE = r'(?:"?public"?\.)?"?([a-z_][a-z0-9_]*)"?'
COMMANDS = {
    "INSERT": re.compile(r"\bINSERT\s+INTO\s+" + TABLE, re.I),
    "UPDATE": re.compile(r"\bUPDATE\s+" + TABLE + r"\s+(?:AS\s+\w+\s+|\w+\s+)?SET\b", re.I),
    "DELETE": re.compile(r"\bDELETE\s+FROM\s+" + TABLE, re.I),
    "SELECT": re.compile(r"\b(?:FROM|JOIN)\s+" + TABLE, re.I),
}
UPSERT = re.compile(r"\bINSERT\s+INTO\s+" + TABLE + r"[^;]*?\bON\s+CONFLICT\b[^;]*?\bDO\s+UPDATE\b", re.I | re.S)
LOCKING = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE)\b", re.I)

# Names after FROM/JOIN that are not public tables: CTEs, catalogs, schemas, functions.
NOT_TABLES = {
    "additional_aliases", "candidate_movements", "changed", "ranked_matches", "repaired",
    "information_schema", "pg_attribute", "pg_catalog", "pg_class", "pg_constraint", "pg_namespace",
    "public", "vault", "set", "select", "lateral", "unnest", "generate_series", "jsonb_array_elements",
    "jsonb_each", "values", "x",
}
# Account deletion deletes, by dynamic SQL, from every table with a foreign key to
# allowed_users (backend/auth/service.py::_delete_allowed_user_dependents).
DYNAMIC_DELETE = {
    "accounts", "advisor_current_strategy", "advisor_strategy_history", "chat_pending_actions", "chat_sessions",
    "financial_input_events", "fixed_expense_matches", "fixed_expenses", "memory_items", "notification_jobs",
}


@lru_cache(maxsize=1)
def _runtime_sql() -> tuple[tuple[str, str], ...]:
    return tuple(_scan_runtime_sql())


def _scan_runtime_sql():
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if relative.startswith(("tests/", "scripts/")) or path.name.startswith("test_") or path.name == "conftest.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            elif isinstance(node, ast.JoinedStr):
                text = "".join(part.value if isinstance(part, ast.Constant) else "{x}" for part in node.values)
            else:
                continue
            if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", text):
                yield relative, text


def needed() -> dict[str, set[str]]:
    need: dict[str, set[str]] = defaultdict(set)
    for _relative, sql in _runtime_sql():
        for command, pattern in COMMANDS.items():
            for match in pattern.finditer(sql):
                need[match.group(1).lower()].add(command)
        for match in UPSERT.finditer(sql):
            need[match.group(1).lower()].add("UPDATE")
        if LOCKING.search(sql) and re.search(r"\bSELECT\b", sql):
            for match in COMMANDS["SELECT"].finditer(sql):
                need[match.group(1).lower()].add("UPDATE")
    for table in DYNAMIC_DELETE:
        need[table].add("DELETE")
    for privileges in need.values():
        privileges.add("SELECT")  # every write here filters or returns rows
    return {table: privileges for table, privileges in need.items() if table not in NOT_TABLES}


def granted() -> dict[str, set[str]]:
    grants: dict[str, set[str]] = defaultdict(set)
    pattern = re.compile(r"GRANT\s+([A-Z, ]+?)\s+ON\s+TABLE\s+public\.(\w+)\s+TO\s+dincr_app\b", re.I)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        for privileges, table in pattern.findall(path.read_text(encoding="utf-8")):
            grants[table.lower()].update(p.strip().upper() for p in privileges.split(","))
    return grants


def test_every_table_and_command_the_backend_uses_is_granted():
    need, grants = needed(), granted()
    missing = {table: sorted(privileges - grants.get(table, set()))
               for table, privileges in need.items() if privileges - grants.get(table, set())}
    assert missing == {}, (
        "The application role (dincr_app) lacks these privileges; add a GRANT ... TO dincr_app "
        f"in the migration that introduces the table or query: {missing}"
    )


def test_the_role_is_not_granted_tables_the_backend_never_uses():
    unused = sorted(set(granted()) - set(needed()))
    assert unused == [], f"Least privilege: remove the grants of tables the backend never uses: {unused}"


def test_the_scanner_sees_what_it_guards():
    sql = """WITH ranked_matches AS (SELECT 1) SELECT * FROM debts d JOIN workspaces w ON true
             WHERE d.id = %s FOR UPDATE"""
    assert COMMANDS["SELECT"].findall(sql) == ["debts", "workspaces"]
    assert LOCKING.search(sql)
    assert UPSERT.search("INSERT INTO t(a) VALUES(1) ON CONFLICT (a) DO UPDATE SET a = 2")
    assert COMMANDS["UPDATE"].findall("UPDATE finva_gmail_connections c SET status='x'") == ["finva_gmail_connections"]


def test_runtime_sql_never_reaches_vault_auth_or_storage_directly():
    """dincr_app has no access to these schemas: mail tokens go through dincr_private."""
    direct = sorted({f"{relative}: {match.group(0)}" for relative, sql in _runtime_sql()
                     for match in re.finditer(r"\b(?:vault|auth|storage)\.[a-z_]+\b", sql)})
    assert direct == [], f"Use dincr_private.mail_secret_* instead of: {direct}"
