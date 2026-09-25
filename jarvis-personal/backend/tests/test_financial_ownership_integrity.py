"""Static guards for the financial ownership integrity work (no database needed).

The behavior against a real PostgreSQL lives in
test_financial_ownership_integrity_pg.py.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend.scripts import financial_ownership_integrity_check as check


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20260925120000_financial_ownership_integrity.sql"
PREFLIGHT = ROOT / "database/audits/financial_ownership_preflight.sql"
EVIDENCE = ROOT / "database/audits/financial_ownership_evidence.sql"
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
    assert _ownership_tables() == re.findall(r"'([a-z_]+)'", array)


def test_migration_is_transactional_and_non_destructive():
    sql = _strip_comments(MIGRATION.read_text(encoding="utf-8"))
    upper = sql.upper()
    assert upper.strip().startswith("BEGIN;") and upper.rstrip().endswith("COMMIT;")
    for forbidden in (
        r"\bDELETE\s+FROM\b", r"\bTRUNCATE\b", r"\bDROP\s+TABLE\b", r"\bDROP\s+COLUMN\b",
        r"\bDROP\s+CONSTRAINT\b", r"\bDROP\s+TRIGGER\b", r"\bVALIDATE\s+CONSTRAINT\b",
        r"\bSET\s+USER_ID\b",
    ):
        assert not re.search(forbidden, upper), forbidden
    # The single data change: workspace_id of rows whose workspace_id is NULL.
    updates = re.findall(r"UPDATE\s+public\.%I\s+t\s+SET\s+(\w+)", sql, re.I)
    assert updates == ["workspace_id"]
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
        sql = _strip_comments(path.read_text(encoding="utf-8")).upper()
        for forbidden in (
            r"\bINSERT\s+INTO\b", r"\bUPDATE\s+[\w.]+\s+(\w+\s+)?SET\b", r"\bDELETE\s+FROM\b",
            r"\bALTER\s+\w+", r"\bDROP\s+\w+", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bCOMMIT\b",
        ):
            assert not re.search(forbidden, sql), (path.name, forbidden)
        # Only session-local functions may be created.
        assert re.findall(r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+([\w]+)\.", sql) in ([], ["PG_TEMP"] * 7)


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
    assert lines[-1] == "RESULT: FAIL (1 of 4 checks failing)"


def test_check_fails_closed_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert check.main() == 2
    assert "DATABASE_URL" in capsys.readouterr().err
