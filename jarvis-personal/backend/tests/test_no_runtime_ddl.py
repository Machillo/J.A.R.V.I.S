"""Request paths never create, alter or drop schema.

Runtime DDL (CREATE/ALTER/DROP/GRANT/REVOKE/TRUNCATE) takes relation-level
locks on every request: concurrent requests deadlocked in PostgreSQL, a read
that "created" a table rolled it back so the table never existed, and an
ALTER TABLE ... IF NOT EXISTS still locks the whole table. Schema belongs in
database/migrations; a path whose table may be missing checks
backend.core.schema_state and degrades explicitly.

LEGACY_OWNER_DDL lists Owner-only modules that still carry DDL. Each count must
match exactly: removing DDL lowers the number in the same change, and no new
module may be added.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

DDL = re.compile(
    r"(?:^|;|\bTHEN\b|\bBEGIN\b|\bELSE\b|\$\$|EXECUTE\s+')\s*"
    r"(?:(?:CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE)\s+"
    r"(?:OR\s+REPLACE\s+|UNIQUE\s+|TEMP(?:ORARY)?\s+|MATERIALIZED\s+)?"
    r"(?:TABLE|INDEX|SCHEMA|SEQUENCE|FUNCTION|PROCEDURE|TRIGGER|VIEW|EXTENSION|POLICY|TYPE|DOMAIN|ROLE|DEFAULT|ALL|SELECT|INSERT|UPDATE|DELETE|USAGE|EXECUTE)\b"
    r"|COMMENT\s+ON\b)",
    re.IGNORECASE,
)
SQL_COMMENT = re.compile(r"--[^\n]*")
# Known limits: DDL assembled by concatenating separate literals, or passed in
# from outside the module, is not seen. This is a guard, not a proof.

LEGACY_OWNER_DDL = {
    "advisor/core.py": 2,
    "ai/memory_service.py": 8,
    "ai/preferences.py": 6,
    "ai/strategy_dashboard.py": 1,
    "deployment_monitor/service.py": 2,
    "email_monitor/service.py": 45,
    "finance/business_center.py": 2,
    "finance/intelligence.py": 24,
    "integrations/ibkr_readonly.py": 17,
}


def _is_runtime_module(relative: str) -> bool:
    name = relative.rsplit("/", 1)[-1]
    return not (
        relative.startswith(("tests/", "scripts/"))
        or name.startswith("test_")
        or name == "conftest.py"
    )


def _ddl_count(path: Path) -> int:
    count = 0
    tree = ast.parse(path.read_text(encoding="utf-8"))
    f_string_parts = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in f_string_parts:
            count += len(DDL.findall(SQL_COMMENT.sub("", node.value)))
        elif isinstance(node, ast.JoinedStr):
            text = "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)
            count += len(DDL.findall(SQL_COMMENT.sub("", text)))
    return count


def _runtime_ddl() -> dict[str, int]:
    found = {}
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if _is_runtime_module(relative) and (count := _ddl_count(path)):
            found[relative] = count
    return found


def test_no_new_module_runs_ddl():
    unexpected = {path: count for path, count in _runtime_ddl().items() if path not in LEGACY_OWNER_DDL}
    assert unexpected == {}, "Move schema changes to database/migrations: " + repr(unexpected)


def test_legacy_owner_ddl_only_shrinks():
    found = _runtime_ddl()
    changed = {path: (ceiling, found.get(path, 0)) for path, ceiling in LEGACY_OWNER_DDL.items() if found.get(path, 0) != ceiling}
    assert changed == {}, "Update LEGACY_OWNER_DDL to the new (lower) count, never raise it: " + repr(changed)


def test_the_scanner_sees_ddl_and_ignores_prose(tmp_path):
    module = tmp_path / "module.py"
    module.write_text(
        'def f(conn):\n'
        '    """Create a flow and drop expired ones."""\n'
        '    conn.execute("CREATE TABLE IF NOT EXISTS t (id INT)")\n'
        '    conn.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")\n'
        '    conn.execute("SELECT 1; REVOKE ALL ON TABLE t FROM anon")\n'
        '    conn.execute("-- keep compatible\\nALTER TABLE t ADD COLUMN IF NOT EXISTS c INT")\n'
        '    conn.execute("DO $$ BEGIN IF true THEN CREATE TRIGGER g AFTER INSERT ON t EXECUTE FUNCTION f(); END IF; END $$")\n'
        '    conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon")\n'
        '    conn.execute("SELECT 1 -- CREATE TABLE in a comment is not DDL")\n',
        encoding="utf-8",
    )
    assert _ddl_count(module) == 6


def test_users_request_modules_have_no_ddl():
    users_modules = ("auth/", "user_product/", "notifications/", "product_ops/", "financial_lifecycle/", "core/")
    found = {path: count for path, count in _runtime_ddl().items() if path.startswith(users_modules)}
    assert found == {}
