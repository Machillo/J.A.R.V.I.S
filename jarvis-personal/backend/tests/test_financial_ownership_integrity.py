"""Static guards for the financial ownership integrity work (no database needed).

The behavior against a real PostgreSQL lives in
test_financial_ownership_integrity_pg.py.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from backend.scripts import financial_ownership_integrity_check as check


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20260925140000_financial_ownership_integrity.sql"
PREFLIGHT = ROOT / "database/audits/financial_ownership_preflight.sql"
EVIDENCE = ROOT / "database/audits/financial_ownership_evidence.sql"
ROLLBACK = ROOT / "database/rollback/20260925140000_financial_ownership_integrity_rollback.sql"
# Financial tables created after Phase 2A that carry the same dual legacy user_id.
POST_PHASE_2A = ["account_balances", "account_balance_history", "net_worth_snapshots", "payroll_salary_reports"]
# Workspace-owned tables whose deletes are NOT guarded, each with the reason.
# Every other table with a workspace_id must be in dincr_delete_guard_tables().
UNGUARDED_WORKSPACE_TABLES = {
    "advisor_current_strategy": "derived strategy snapshot (Owner), recomputed",
    **{f"audit_backup_{name}_20260908": "static copy from a past manual cleanup; never written by the app"
       for name in ("goal_schedules", "goals", "receivable_entries", "receivable_payments", "receivables")},
    "advisor_strategy_history": "derived strategy history (Owner)",
    "finva_parser_fallback_events": "parser diagnostic log",
    "ai_premium_guides": "AI usage bookkeeping (Owner), no financial truth",
    "ai_premium_settings": "AI settings (Owner)",
    "ai_premium_usage_events": "usage counter",
    "ai_usage_daily": "usage counter",
    "ai_usage_events": "usage counter",
    "billing_orders": "off-store billing, retired (20260926120000_retire_offstore_billing)",
    "billing_subscriptions": "off-store billing, retired (20260926120000_retire_offstore_billing)",
    "chat_pending_actions": "Owner assistant state",
    "chat_sessions": "Owner assistant state",
    "email_classification_rules": "Owner mail configuration",
    "email_monitor_settings": "Owner mail configuration",
    "email_parser_logs": "diagnostic log",
    "feedback_reports": "support reports",
    "financial_health_snapshots": "derived snapshot, recomputed",
    "financial_state_snapshots": "derived snapshot, recomputed",
    "finva_gmail_consents": "consent ledger, append-only by design",
    "finva_gmail_oauth_states": "short-lived OAuth state",
    "logs": "diagnostic log",
    "mail_oauth_flows": "short-lived OAuth flow",
    "memory_items": "Owner assistant memory",
    "notification_jobs": "notification queue",
    "notification_subscriptions": "push endpoints",
    "product_events": "analytics events",
    "store_subscriptions": "store entitlement, rebuilt from the store",
    "user_preferences": "preferences",
    "workspace_members": "membership, not financial data",
}
SCHEMA = ROOT / "database/schema.sql"
BACKEND = ROOT / "backend"


def _ownership_tables() -> list[str]:
    block = MIGRATION.read_text(encoding="utf-8")
    body = block[block.index("dincr_ownership_tables()"):block.index("AS t(table_name")]
    return re.findall(r"\('([a-z_]+)',", body)


def _strip_comments(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def test_ownership_table_list_matches_phase_2a():
    schema = SCHEMA.read_text(encoding="utf-8")
    phase_2a = schema[schema.index("Unified JARVIS workspace ownership - Phase 2A"):]
    array = phase_2a[phase_2a.index("ARRAY["):phase_2a.index("];")]
    assert _ownership_tables() == re.findall(r"'([a-z_]+)'", array) + POST_PHASE_2A


def test_migration_is_transactional_and_non_destructive():
    sql = _strip_comments(MIGRATION.read_text(encoding="utf-8"))
    # Dynamic DDL templates are checked too; only the two TRUNCATE-guard strings
    # (its trigger definition and its error message) are allowed.
    upper = sql.upper().replace("BEFORE TRUNCATE ON", "").replace("'TRUNCATE OF FINANCIAL TABLE", "'")
    assert upper.strip().startswith("BEGIN;") and upper.rstrip().endswith("COMMIT;")
    for forbidden in (
        r"\bDELETE\s+FROM\b", r"\bTRUNCATE\b", r"\bDROP\s+TABLE\b", r"\bDROP\s+COLUMN\b",
        r"\bDROP\s+CONSTRAINT\b", r"\bDROP\s+TRIGGER\b", r"\bVALIDATE\s+CONSTRAINT\b",
        r"\bSET\s+USER_ID\b",
    ):
        assert not re.search(forbidden, upper), forbidden
    # The single data change: workspace_id of rows whose workspace_id is NULL.
    statements = re.findall(r"\bUPDATE\s+(?!OF\b)(?:ONLY\s+)?(\S+)(?:\s+(?:AS\s+)?\w+)?\s+SET\s+(\w+)", sql, re.I)
    assert statements == [("public.%I", "workspace_id")]
    assert "AND t.workspace_id IS NULL" in sql
    assert "a.classification = 'SAFE_AUTO_FIX'" in sql
    # Every new constraint leaves existing rows alone (NOT VALID).
    for statement in re.findall(r"ADD CONSTRAINT[^;]*", sql):
        assert "NOT VALID" in statement
    # The guard never blocks edits of other columns on rows under review.
    assert "BEFORE INSERT OR UPDATE OF user_id, workspace_id" in sql


def test_preflight_uses_the_migration_audit_functions_verbatim():
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    start = preflight.index(check.BLOCK_START)
    end = preflight.index(check.BLOCK_END) + len(check.BLOCK_END)
    assert preflight[start:end] == check.audit_functions_sql("pg_temp")
    assert "public.dincr_" not in _strip_comments(preflight)
    assert "SET LOCAL transaction_read_only = on;" in preflight
    assert "COMMIT" not in _strip_comments(preflight).upper()


def test_audit_sql_files_are_read_only():
    for path in (PREFLIGHT, EVIDENCE):
        # Quoted literals (e.g. a regex listing statement kinds) are data, not SQL.
        sql = re.sub(r"'(?:[^']|'')*'", "''", _strip_comments(path.read_text(encoding="utf-8"))).upper()
        for forbidden in (
            r"\bINSERT\s+INTO\b", r"\bUPDATE\s+(ONLY\s+)?[\w.\"]+\s+(\w+\s+)?SET\b", r"\bDELETE\s+FROM\b",
            r"\bALTER\s+\w+", r"\bDROP\s+\w+", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bCOMMIT\b",
            r"\bCREATE\s+(TABLE|INDEX|UNIQUE|VIEW|SCHEMA|TRIGGER|ROLE|EXTENSION)\b", r"\bINTO\s+(TEMP|TEMPORARY|UNLOGGED|TABLE)\b",
            r"\bCOPY\b", r"\bSETVAL\b", r"\bNEXTVAL\b", r"\bVACUUM\b", r"\bREINDEX\b", r"\bCALL\b",
            r"\bDO\s+(\$|LANGUAGE|')",
        ):
            assert not re.search(forbidden, sql), (path.name, forbidden)
        if path == EVIDENCE:
            # Dynamic SQL hides statements from these checks; only the preflight's
            # temp functions use it, inside a READ ONLY transaction.
            assert not re.search(r"\bEXECUTE\b", sql)
        # Only session-local functions may be created.
        assert re.findall(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+([\w]+)\.", sql) in ([], ["PG_TEMP"] * 10)


def test_every_guarded_insert_sets_its_workspace():
    """Writers of workspace-only guarded tables must satisfy their CHECK from day one."""
    extras = sorted(_delete_guard_tables() - set(_ownership_tables()))
    pattern = re.compile(rf"INSERT\s+INTO\s+(?:public\.)?({'|'.join(extras)})\s*\(([^)]*)\)", re.I | re.S)
    offenders, seen = [], 0
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            seen += 1
            if "workspace_id" not in {c.strip().lower() for c in match.group(2).split(",")}:
                offenders.append(f"{path.relative_to(ROOT)}:{text[: match.start()].count(chr(10)) + 1} {match.group(1)}")
    assert seen > 10
    assert offenders == []


def test_every_financial_insert_sets_workspace_and_user():
    """New writers must satisfy the ownership CHECK and trigger from day one."""
    tables = "|".join(_ownership_tables())
    pattern = re.compile(rf"INSERT\s+INTO\s+(?:public\.)?({tables})\s*\(([^)]*)\)", re.I | re.S)
    offenders, seen = [], 0
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            seen += 1
            columns = {c.strip().lower() for c in match.group(2).split(",")}
            if not {"workspace_id", "user_id"} <= columns:
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(ROOT)}:{line} {match.group(1)}")
    assert seen > 40  # the scan really finds the writers
    assert offenders == []


# Comparisons on user_id that exist today, each on a table written only with
# allowed_users.id. Tracked for removal (canonical identity plan, Phase C).
KNOWN_USER_ID_COMPARISONS = {
    ("backend/notifications/service.py", "au.id = ns.user_id"),  # notification_subscriptions: FK -> allowed_users
    ("backend/notifications/service.py", "au.id = e.user_id"),   # events: written by core/events with allowed_users.id
    ("backend/notifications/service.py", "au.id = fe.user_id"),  # fixed_expenses: Owner-only writer, allowed_users.id
}


def _sql_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def test_no_backend_query_decides_by_legacy_user_id():
    """Ownership is workspace_id. A SQL comparison on user_id (either side, any
    operator) would let the two legacy id spaces (allowed_users.id vs users.id)
    be confused again. Only string literals are scanned, so Python is ignored."""
    comparison = re.compile(
        r"(?<![\w.])(?:\w+\.)?user_id\s*(?:=(?!\s*EXCLUDED\.)|<>|!=|\bIN\b|\bIS\b)"
        r"|(?:=|<>|!=)\s*\(?\s*(?!EXCLUDED\.)(?:\w+\.)?user_id\b",
        re.I,
    )
    found = set()
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        for literal in _sql_literals(path):
            if not re.search(r"\b(SELECT|UPDATE|DELETE|JOIN|WHERE)\b", literal, re.I):
                continue
            for match in comparison.finditer(literal):
                start = max(literal.rfind("\n", 0, match.start()) + 1, 0)
                end = literal.find("\n", match.end())
                line = literal[start:end if end != -1 else None].strip()
                snippet = next((known for file, known in KNOWN_USER_ID_COMPARISONS if known in line), line)
                found.add((str(path.relative_to(ROOT)), snippet))
    assert found == KNOWN_USER_ID_COMPARISONS


def test_rollback_only_removes_guards():
    sql = _strip_comments(ROLLBACK.read_text(encoding="utf-8")).upper()
    assert sql.strip().startswith("BEGIN;") and sql.rstrip().endswith("COMMIT;")
    for forbidden in (r"\bDELETE\s+FROM\b", r"\bTRUNCATE\b", r"\bDROP\s+TABLE\b", r"\bDROP\s+COLUMN\b", r"\bUPDATE\s+"):
        assert not re.search(forbidden, sql), forbidden


def test_report_prints_counts_only_and_fails_on_findings():
    summary = [
        ("debts", "OK", "OK", 7),
        ("debts", "OK", "OK_ID_SPACE_COLLISION", 5),
        ("debts", "NEEDS_REVIEW", "USER_ID_FOREIGN", 2),
        ("debt_payments", "OK", "OK", 10),
        ("_identity", "INFO", "USERS_ROW_WITHOUT_ACCOUNT", 3),
    ]
    results = {r["table"]: r for r in check.evaluate(summary, ["debts", "debt_payments", "receivables"])}
    assert results["debts"]["status"] == "FAIL"
    assert results["debts"]["rows"] == 14
    assert results["debt_payments"]["status"] == "PASS"
    assert results["receivables"] == {"table": "receivables", "status": "PASS", "rows": 0, "counts": {}, "issues": {}}
    assert results["_identity"]["status"] == "PASS"
    lines = check.render(list(results.values()))
    assert "FAIL | debts | rows=14 ok=12" in lines
    assert "    NEEDS_REVIEW USER_ID_FOREIGN: 2" in lines
    assert "    OK OK_ID_SPACE_COLLISION: 5" in lines
    assert lines[-1] == "RESULT: FAIL (1 of 4 checks failing)"


def test_check_fails_closed_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert check.main() == 2
    assert "DATABASE_URL" in capsys.readouterr().err


class _RoleCursor:
    def __init__(self, bypass): self.bypass, self.sql = bypass, []
    def execute(self, sql): self.sql.append(sql)
    def fetchone(self): return (self.bypass,)


class _RoleConnection:
    def __init__(self, bypass): self.cur, self.rolled_back = _RoleCursor(bypass), False
    def cursor(self): return self.cur
    def rollback(self): self.rolled_back = True


def test_check_refuses_a_role_subject_to_rls():
    conn = _RoleConnection(bypass=False)
    try:
        check.collect_summary(conn)
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    assert len(conn.cur.sql) == 1 and conn.rolled_back  # nothing else ran


def test_admin_promoted_in_allowed_users_is_checked_too():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "au.role IN ('owner', 'admin') AND au.status = 'active'" in sql


def test_the_migration_is_one_transaction_the_reviewed_runner_accepts():
    from backend.scripts import apply_migration

    sql = MIGRATION.read_text(encoding="utf-8")
    apply_migration.check_single_transaction(sql)
    assert MIGRATION.parent.name == "migrations"
    statements = apply_migration.statements(sql)
    assert "SET LOCAL lock_timeout = '5s'" in statements[1:4]


def test_the_migration_requires_the_request_path_schema_first():
    """Its deletion guards cover the Basic tables; they must exist when it runs."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "apply 20260925130000_request_path_schema.sql first" in sql
    assert (MIGRATION.parent / "20260925130000_request_path_schema.sql").exists()



def _delete_guard_tables() -> set[str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    body = sql[sql.index("FUNCTION public.dincr_delete_guard_tables()"):]
    body = body[:body.index("AS t(table_name)")]
    return set(_ownership_tables()) | set(re.findall(r"\('([a-z_]+)'\)", body))


def _repo_workspace_tables() -> set[str]:
    """Tables the repository's SQL creates with a workspace_id column."""
    found = set()
    sources = [SCHEMA, *sorted((ROOT / "database" / "migrations").glob("*.sql")),
               *sorted((ROOT / "database" / "baseline").glob("*.sql"))]
    for path in sources:
        sql = _strip_comments(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?\"?([a-z_]+)\"?\s*\((.*?)\n\);", sql, re.I | re.S):
            if re.search(r"\bworkspace_id\b", match.group(2)):
                found.add(match.group(1).lower())
        for match in re.finditer(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?\"?([a-z_]+)\"?\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?workspace_id\b", sql, re.I):
            found.add(match.group(1).lower())
    return found - {"workspaces"}


def test_every_workspace_table_is_guarded_or_explicitly_exempt():
    guarded, exempt = _delete_guard_tables(), set(UNGUARDED_WORKSPACE_TABLES)
    assert not guarded & exempt, guarded & exempt
    unclassified = _repo_workspace_tables() - guarded - exempt
    assert unclassified == set(), "Add each table to dincr_delete_guard_tables() or UNGUARDED_WORKSPACE_TABLES with a reason"


def test_preflight_lists_the_same_delete_guard_tables_as_the_migration():
    preflight = (ROOT / "database" / "audits" / "financial_ownership_preflight.sql").read_text(encoding="utf-8")
    lists = [preflight[:end].rsplit("(VALUES", 1)[1] for end in
             (m.start() for m in re.finditer(r"AS d\(table_name\)", preflight))]
    assert len(lists) == 3  # rows without a workspace, colliding ids, unguarded workspace tables
    for block in lists:
        assert set(re.findall(r"\('([a-z_]+)'\)", block)) == _delete_guard_tables() - set(_ownership_tables())
