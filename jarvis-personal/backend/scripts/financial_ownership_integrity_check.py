"""Financial ownership integrity check (release gate).

Usage (from jarvis-personal/, DATABASE_URL pointing at the database to check):

    python backend/scripts/financial_ownership_integrity_check.py

Prints PASS/FAIL per financial table plus the identity core, and exits 1 when
any table has a SAFE_AUTO_FIX, NEEDS_REVIEW or ORPHAN row.

Read-only: the audit functions come from the ownership migration and are
created as pg_temp functions inside a transaction that is switched to READ ONLY
before the audit runs and is always rolled back. It works before and after the
migration is applied. Output is counts only: no row ids, names, emails,
amounts, descriptions or connection details.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20260925120000_financial_ownership_integrity.sql"
BLOCK_START = "-- BEGIN DINCR OWNERSHIP AUDIT FUNCTIONS"
BLOCK_END = "-- END DINCR OWNERSHIP AUDIT FUNCTIONS"
FAILING = ("SAFE_AUTO_FIX", "NEEDS_REVIEW", "ORPHAN")


def audit_functions_sql(schema: str = "pg_temp") -> str:
    """The migration's audit function block, retargeted to `schema`."""
    text = MIGRATION.read_text(encoding="utf-8")
    start = text.index(BLOCK_START)
    end = text.index(BLOCK_END) + len(BLOCK_END)
    return text[start:end].replace("public.dincr_", f"{schema}.dincr_")


def collect_summary(conn) -> tuple[list[tuple[str, str, str, int]], list[str]]:
    """Audit counts plus the audited tables present, from a rolled-back, read-only run."""
    cursor = conn.cursor()
    try:
        # The audit runs with the caller's rights: a role subject to RLS would see
        # no rows and report a false PASS.
        cursor.execute(
            "SELECT rolsuper OR rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = current_user"
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            raise PermissionError("The database role must bypass RLS to audit every row.")
        cursor.execute(audit_functions_sql("pg_temp"))
        cursor.execute("SET LOCAL transaction_read_only = on")
        cursor.execute(
            "SELECT table_name, classification, issue, row_count "
            "FROM pg_temp.dincr_ownership_audit_summary()"
        )
        summary = [(str(r[0]), str(r[1]), str(r[2]), int(r[3])) for r in cursor.fetchall()]
        cursor.execute(
            "SELECT table_name FROM pg_temp.dincr_ownership_tables() "
            "WHERE to_regclass(format('public.%I', table_name)) IS NOT NULL"
        )
        present = [str(r[0]) for r in cursor.fetchall()]
        return summary, present
    finally:
        conn.rollback()


def evaluate(summary: list[tuple[str, str, str, int]], present: list[str] = ()) -> list[dict]:
    tables: dict[str, dict] = defaultdict(lambda: {"rows": 0, "counts": defaultdict(int), "issues": defaultdict(int)})
    for table in (*present, "_identity"):
        tables[table]  # empty tables still get a PASS line
    for table, classification, issue, count in summary:
        entry = tables[table]
        entry["counts"][classification] += count
        if classification != "INFO" and table != "_identity":
            entry["rows"] += count
        # Collisions and canonical rows are OK but still shown: a PASS must not hide
        # the rows whose legacy id is ambiguous across the two id spaces.
        if classification != "OK" or issue != "OK":
            entry["issues"][(classification, issue)] += count
    results = []
    for table in sorted(tables):
        entry = tables[table]
        failed = any(entry["counts"].get(c, 0) for c in FAILING)
        results.append({
            "table": table,
            "status": "FAIL" if failed else "PASS",
            "rows": entry["rows"],
            "counts": dict(entry["counts"]),
            "issues": dict(entry["issues"]),
        })
    return results


def render(results: list[dict]) -> list[str]:
    lines = []
    for result in results:
        counts = result["counts"]
        head = f"{result['status']} | {result['table']}"
        if result["table"] != "_identity":
            head += f" | rows={result['rows']} ok={counts.get('OK', 0)}"
        lines.append(head)
        for (classification, issue), count in sorted(result["issues"].items()):
            lines.append(f"    {classification} {issue}: {count}")
    failed = [r["table"] for r in results if r["status"] == "FAIL"]
    lines.append("")
    lines.append(f"RESULT: {'FAIL' if failed else 'PASS'} ({len(failed)} of {len(results)} checks failing)")
    return lines


def main() -> int:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    import psycopg2

    try:
        conn = psycopg2.connect(dsn)
    except Exception as exc:  # never echo the DSN
        print(f"Could not connect to the database ({type(exc).__name__}).", file=sys.stderr)
        return 2
    try:
        results = evaluate(*collect_summary(conn))
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        conn.close()
    for line in render(results):
        print(line)
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
