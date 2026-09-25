"""Request paths never create, alter or drop schema.

Runtime DDL (CREATE/ALTER/DROP/GRANT/REVOKE/TRUNCATE) takes relation-level
locks on every request: concurrent requests deadlocked in PostgreSQL, a read
that "created" a table rolled it back so the table never existed, and an
ALTER TABLE ... IF NOT EXISTS still locks the whole table. Schema belongs in
database/migrations; a path whose table may be missing checks
backend.core.schema_state and degrades explicitly.

LEGACY_OWNER_DDL lists modules that still carry DDL outside Users request paths
(test_users_routes_never_reach_ddl proves no Users route reaches it). Each count must
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
# Known limits: DDL assembled by concatenating separate literals, SQL kept in
# module-level constants, method calls on objects (self.m(), obj.m()) and
# unaliased dotted imports (import backend.x.y; backend.x.y.f()) are not
# followed. This is a guard, not a proof.

LEGACY_OWNER_DDL = {
    "advisor/core.py": 2,
    "ai/memory_service.py": 8,
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


# ---- Call-graph guard: what a Users request can reach ----------------------
# Scanning Users directories is not enough: a Users route can call into a
# shared module (finance, advisor, integrations) that runs DDL. This follows
# calls from every Users route through module imports and fails if any
# reachable function contains DDL.
USERS_ROUTE_MODULES = ("user_product/routes.py", "financial_lifecycle/routes.py", "auth/routes.py",
                       "product_ops/routes.py", "notifications/routes.py")


def _module_name(relative: str) -> str:
    return "backend." + relative[:-3].replace("/", ".")


def _call_graph():
    functions, calls = {}, {}
    for path in sorted(BACKEND.rglob("*.py")):
        relative = path.relative_to(BACKEND).as_posix()
        if not _is_runtime_module(relative):
            continue
        module = _module_name(relative)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend"):
                for alias in node.names:
                    imported[alias.asname or alias.name] = (node.module, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("backend"):
                        imported[alias.asname or alias.name] = (alias.name, None)
        for node in tree.body:
            for fn in ([node] if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else
                       [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))] if isinstance(node, ast.ClassDef) else []):
                key = f"{module}.{fn.name}"
                functions[key] = fn
                targets = set()
                # Every reference counts, not only calls: a function passed as a
                # callback (Depends(fn), _safe(fn), executor.submit(fn)) runs too.
                for ref in ast.walk(fn):
                    if isinstance(ref, ast.Name):
                        if ref.id in imported:
                            source, name = imported[ref.id]
                            targets.add(f"{source}.{name or ref.id}")
                        else:
                            targets.add(f"{module}.{ref.id}")
                    elif isinstance(ref, ast.Attribute) and isinstance(ref.value, ast.Name) and ref.value.id in imported:
                        source, name = imported[ref.value.id]
                        targets.add(f"{source}.{name}.{ref.attr}" if name else f"{source}.{ref.attr}")
                calls[key] = targets
    return functions, calls


def _function_has_ddl(fn) -> bool:
    parts = {id(part) for node in ast.walk(fn) if isinstance(node, ast.JoinedStr) for part in node.values}
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in parts:
            if DDL.search(SQL_COMMENT.sub("", node.value)):
                return True
        elif isinstance(node, ast.JoinedStr):
            text = "".join(p.value if isinstance(p, ast.Constant) else "{}" for p in node.values)
            if DDL.search(SQL_COMMENT.sub("", text)):
                return True
    return False


# Call edges Users never take at runtime; each names its proof (a test below).
GUARDED_EDGES = {
    # build_advisor_strategy persists (DDL + writes) only when persist=True; every
    # Users-reachable caller passes persist=False
    # (test_users_build_the_advisor_strategy_without_persisting_it).
    ("backend.advisor.core.build_advisor_strategy", "backend.advisor.core._persist_strategy"),
}


def _users_reachable(entry_modules=USERS_ROUTE_MODULES, guarded=GUARDED_EDGES):
    functions, calls = _call_graph()
    entries = [key for key in functions if any(key.startswith(_module_name(m) + ".") for m in entry_modules)]
    seen, stack, parent = set(entries), list(entries), {}
    while stack:
        current = stack.pop()
        for target in calls.get(current, ()):
            if (current, target) in guarded:
                continue
            if target in functions and target not in seen:
                seen.add(target)
                parent[target] = current
                stack.append(target)
    return functions, calls, seen, parent


def _reachable_ddl(entry_modules=USERS_ROUTE_MODULES, guarded=GUARDED_EDGES):
    functions, _, seen, parent = _users_reachable(entry_modules, guarded)
    found = {}
    for key in sorted(seen):
        if _function_has_ddl(functions[key]):
            chain, node = [key], key
            while node in parent:
                node = parent[node]
                chain.append(node)
            found[key] = " <- ".join(reversed(chain[-6:]))
    return found


def test_users_routes_never_reach_ddl():
    assert _reachable_ddl() == {}, "A Users request path reaches runtime DDL; move it to a migration"


def test_users_build_the_advisor_strategy_without_persisting_it():
    functions, calls, seen, _ = _users_reachable()
    callers = [key for key in seen if "backend.advisor.core.build_advisor_strategy" in calls.get(key, ())
               and key != "backend.advisor.core.build_advisor_strategy"]
    assert callers, "the guarded edge is obsolete; remove it from GUARDED_EDGES"
    for key in callers:
        invocations = [node for node in ast.walk(functions[key]) if isinstance(node, ast.Call)
                       and getattr(node.func, "id", getattr(node.func, "attr", None)) == "build_advisor_strategy"]
        assert invocations, f"{key} references build_advisor_strategy without calling it"
        for node in invocations:
            persist = [kw.value for kw in node.keywords if kw.arg == "persist"]
            assert persist and isinstance(persist[0], ast.Constant) and persist[0].value is False, key
    core = (BACKEND / "advisor" / "core.py").read_text(encoding="utf-8")
    assert "_persist_strategy(strategy) if persist else" in core


def test_the_call_graph_guard_follows_calls_across_modules():
    # The guard found DDL reached from a VIP route through finance.service and
    # ai.preferences; keep it able to see a chain like that.
    _, calls = _call_graph()
    assert "backend.finance.emergency_fund.update_salvavidas" in calls["backend.user_product.routes.vip_salvavidas_update"]
    assert "backend.advisor.core.build_advisor_strategy" in calls["backend.financial_lifecycle.state._build_financial_state"]
