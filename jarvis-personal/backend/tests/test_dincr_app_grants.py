"""The application role (dincr_app) is granted exactly what the backend's SQL needs.

The backend connects as dincr_app, which has only explicit per-table privileges
(database/migrations/20260926150000_dincr_app_role.sql and later migrations). A
query on a table or with a command the role was not granted fails in production
with "permission denied". This test reads the SQL the runtime code runs and every
"GRANT ... ON TABLE public.<t> TO dincr_app" in the migrations, and fails when the
code needs more than is granted. A new table or command therefore ships with its
GRANT in the migration that introduces it.

Known limits (it is a guard, not a proof): SQL assembled from separate literals is
not followed. SQL whose table name is interpolated must be declared in DYNAMIC_SITES,
either with the tables it can reach or with the catalog rule the role migration
grants from.
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
LOCKING = re.compile(r"\bFOR\s+(?:NO\s+KEY\s+)?(?:KEY\s+)?(?:UPDATE|SHARE)\b(?:\s+OF\s+(\w+(?:\s*,\s*\w+)*))?", re.I)
# FROM/JOIN <table> [AS] <alias>: a row lock with OF <alias> needs UPDATE only on that table.
ALIASED = re.compile(r"\b(?:FROM|JOIN)\s+" + TABLE + r"(?:\s+AS)?\s+(?!ON\b|WHERE\b|JOIN\b|LEFT\b|INNER\b|USING\b)(\w+)", re.I)

# Names after FROM/JOIN that are not public tables: CTEs, catalogs, schemas, functions.
NOT_TABLES = {
    "additional_aliases", "candidate_movements", "changed", "ranked_matches", "repaired",
    "information_schema", "pg_attribute", "pg_catalog", "pg_class", "pg_constraint", "pg_namespace",
    "public", "vault", "set", "select", "lateral", "unnest", "generate_series", "jsonb_array_elements",
    "jsonb_each", "values", "x",
}
# SQL whose table name is interpolated: (module, command) -> the tables it can reach,
# or the catalog rule 20260926150000 grants from (a marker string in that migration).
DYNAMIC_SITES: dict[tuple[str, str], set[str] | str] = {
    # Free movements: {"salary": "salaries", "expense": "expenses", "payroll": "payroll_events"}.
    ("user_product/free_service.py", "DELETE"): {"salaries", "expenses", "payroll_events"},
    # Account deletion: every table with a foreign key to allowed_users.
    ("auth/service.py", "DELETE"): "c.confrelid = 'public.allowed_users'::regclass",
    # Personal data export: every table with account_id or workspace_id.
    ("auth/data_export.py", "SELECT"): "a.attname IN ('account_id', 'workspace_id')",
}
DYNAMIC_TABLE = re.compile(r'\b(DELETE\s+FROM|UPDATE|INSERT\s+INTO|FROM|JOIN)\s+"?(?:\{x\}"?\."?)?\{x\}', re.I)


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
        lock = LOCKING.search(sql)
        if lock and re.search(r"\bSELECT\b", sql):
            if lock.group(1):  # FOR ... OF a, b: only those tables are locked
                aliases = {alias.lower(): table.lower() for table, alias in ALIASED.findall(sql)}
                for name in (part.strip().lower() for part in lock.group(1).split(",")):
                    need[aliases.get(name, name)].add("UPDATE")
            else:
                for match in COMMANDS["SELECT"].finditer(sql):
                    need[match.group(1).lower()].add("UPDATE")
    for (_module, command), reach in DYNAMIC_SITES.items():
        for table in reach if isinstance(reach, set) else ():
            need[table].add(command)
    for privileges in need.values():
        privileges.add("SELECT")  # every write here filters or returns rows
    return {table: privileges for table, privileges in need.items() if table not in NOT_TABLES}


def retired() -> set[str]:
    """Tables a migration drops. Their grants go with them (e.g. the off-store billing
    tables that 20260926152000 retires after 20260926150000 granted them)."""
    pattern = re.compile(r"^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(\w+)", re.I | re.M)
    return {table.lower() for path in MIGRATIONS.glob("*.sql") for table in pattern.findall(path.read_text(encoding="utf-8"))}


def granted() -> dict[str, set[str]]:
    grants: dict[str, set[str]] = defaultdict(set)
    pattern = re.compile(r"GRANT\s+([A-Z, ]+?)\s+ON\s+TABLE\s+public\.(\w+)\s+TO\s+dincr_app\b", re.I)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        for privileges, table in pattern.findall(path.read_text(encoding="utf-8")):
            grants[table.lower()].update(p.strip().upper() for p in privileges.split(","))
    for table in retired():
        grants.pop(table, None)
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


def _command(verb: str) -> str:
    verb = " ".join(verb.upper().split())
    return {"DELETE FROM": "DELETE", "INSERT INTO": "INSERT", "UPDATE": "UPDATE"}.get(verb, "SELECT")


def test_every_interpolated_table_name_is_declared():
    found = {(relative, _command(match.group(1))) for relative, sql in _runtime_sql() for match in DYNAMIC_TABLE.finditer(sql)}
    assert found == set(DYNAMIC_SITES), (
        "SQL with an interpolated table name must be declared in DYNAMIC_SITES (and granted): "
        f"undeclared {sorted(found - set(DYNAMIC_SITES))}, stale {sorted(set(DYNAMIC_SITES) - found)}"
    )
    role = (MIGRATIONS / "20260926150000_dincr_app_role.sql").read_text(encoding="utf-8")
    for reach in DYNAMIC_SITES.values():
        if isinstance(reach, str):
            assert reach in role, f"the role migration no longer grants from: {reach}"


# 20260926150000 grants sequence USAGE, the catalog-rule privileges and the
# dincr_app_access policy only for the tables that exist when it runs. A later
# migration must carry its own: without sequence USAGE an INSERT fails (42501),
# without a policy the table silently reads as empty (unknown is not zero), and
# without SELECT the export silently skips it and account deletion fails.
ROLE_MIGRATION = "20260926150000_dincr_app_role.sql"
CREATE_TABLE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + TABLE + r"\s*\(", re.I)


def _table_bodies(sql: str):
    for match in CREATE_TABLE.finditer(sql):
        depth, end = 1, match.end()
        while depth and end < len(sql):
            depth += {"(": 1, ")": -1}.get(sql[end], 0)
            end += 1
        yield match.group(1).lower(), sql[match.end():end]


def role_gaps(later: dict[str, str]) -> list[str]:
    """What later migrations (name -> SQL) leave the application role without."""
    text = "\n".join(later.values())
    table_grants = {t.lower() for _p, t in re.findall(r"GRANT\s+([A-Z, ]+?)\s+ON\s+TABLE\s+public\.(\w+)\s+TO\s+dincr_app\b", text, re.I)}
    policies = {t.lower() for t in re.findall(r"CREATE\s+POLICY\s+\w+\s+ON\s+(?:public\.)?(\w+)[^;]*?\bTO\s+dincr_app\b", text, re.I | re.S)}
    gaps = []
    for name, sql in sorted(later.items()):
        for table, body in _table_bodies(sql):
            if re.search(r"\b(?:BIG)?SERIAL\b|\bGENERATED\s+(?:ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b", body, re.I) \
                    and table in table_grants and not re.search(r"GRANT\s+USAGE\s+ON\s+SEQUENCE\s+[^;]*\b" + table, text, re.I):
                gaps.append(f"{name}: {table} is granted to dincr_app but not its sequence (GRANT USAGE ON SEQUENCE)")
            if re.search(r"\b(?:account_id|workspace_id)\b|REFERENCES\s+(?:public\.)?allowed_users\b", body, re.I) \
                    and table not in table_grants:
                gaps.append(f"{name}: {table} has account/workspace ownership or an allowed_users FK but no GRANT to dincr_app "
                            "(the export would skip it; account deletion would fail)")
    for table in sorted(table_grants - policies):
        gaps.append(f"{table} is granted to dincr_app in a later migration without CREATE POLICY ... TO dincr_app")
    return gaps


def test_migrations_after_the_role_carry_its_privileges():
    later = {path.name: path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS.glob("*.sql")) if path.name > ROLE_MIGRATION}
    assert role_gaps(later) == [], "A migration after the role migration must grant dincr_app what it needs: " + repr(role_gaps(later))


def test_the_role_gap_check_sees_what_it_guards():
    new_table = "CREATE TABLE IF NOT EXISTS public.widgets (id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL);"
    assert len(role_gaps({"x.sql": new_table})) == 1  # ownership column, no grant
    granted_only = new_table + "\nGRANT SELECT, INSERT ON TABLE public.widgets TO dincr_app;"
    assert len(role_gaps({"x.sql": granted_only})) == 2  # no sequence usage, no policy
    complete = granted_only + ("\nGRANT USAGE ON SEQUENCE public.widgets_id_seq TO dincr_app;"
                               "\nCREATE POLICY dincr_app_access ON public.widgets AS PERMISSIVE FOR ALL TO dincr_app USING (true);")
    assert role_gaps({"x.sql": complete}) == []
    assert role_gaps({"x.sql": "ALTER TABLE public.salaries ADD COLUMN IF NOT EXISTS original_amount NUMERIC(14,2);"}) == []
