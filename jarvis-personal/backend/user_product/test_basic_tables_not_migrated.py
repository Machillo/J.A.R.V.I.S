"""Basic's own tables come from a migration, never from a request.

Regression: request paths used to run CREATE TABLE for the Basic tables inside
every read (rolled back, so the tables never existed), while the Users Strategy
income baseline read finva_recurring_items without that DDL and failed with
"relation does not exist" for every non-Owner account.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.user_product import basic_service, income_policy

WORKSPACE = "workspace-basic-a"
ACCOUNT = "account-basic-a"
BASIC = {"finva_budget_items", "finva_recurring_items", "finva_goal_contributions"}
DDL = ("CREATE ", "ALTER ", "DROP ", "REVOKE ", "GRANT ", "TRUNCATE ")


class UndefinedTable(Exception):
    pass


class NotMigratedConn:
    """PostgreSQL without the Basic migration: its tables do not exist."""

    def __init__(self):
        self.queries: list[str] = []

    def execute(self, query, params=()):
        q = " ".join(query.split())
        self.queries.append(q)
        if q.upper().startswith(DDL):
            raise AssertionError(f"request path ran DDL: {q[:80]}")
        if "to_regclass('public.' || t) IS NULL" in q:
            missing = sorted(t for t in params[0] if t in BASIC)
            return self._result([{"missing": missing or None}])
        if any(table in q for table in BASIC):
            raise UndefinedTable(q[:80])
        if "FROM financial_profiles" in q:
            return self._result([])
        if q.startswith("SELECT COALESCE((SELECT SUM(amount) FROM salaries"):
            return self._result([{"income": 0, "expenses": 0, "debt_paid": 0}])
        if "to_char(transaction_date::date,'YYYY-MM')" in q:
            return self._result([])
        if "SELECT COALESCE(SUM(monthly_payment),0) total FROM debts" in q:
            return self._result([{"total": 0}])
        if "GROUP BY category" in q or "FROM debts WHERE workspace_id=%s AND remaining_amount>0" in q \
                or "FROM financial_goals WHERE workspace_id=%s AND status='active' AND target_date" in q:
            return self._result([])
        raise AssertionError(f"unexpected query: {q[:100]}")

    @staticmethod
    def _result(rows):
        return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)

    def commit(self):
        raise AssertionError("a read committed")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def conn(monkeypatch):
    connection = NotMigratedConn()
    monkeypatch.setattr(basic_service, "get_connection", lambda: connection)
    monkeypatch.setattr(basic_service, "get_current_account_id", lambda: ACCOUNT)
    monkeypatch.setattr(basic_service, "get_current_workspace_id", lambda: WORKSPACE)
    return connection


def test_strategy_income_baseline_works_before_the_basic_migration(conn):
    result = income_policy.load_income_baseline(conn, account_id=ACCOUNT, workspace_id=WORKSPACE)

    assert result["recurring"] == 0
    assert not any("FROM finva_recurring_items" in q for q in conn.queries)


def test_basic_reads_show_no_items_instead_of_creating_tables(conn):
    assert basic_service.list_recurring_items()["items"] == []
    budget = basic_service.get_guided_budget()
    assert budget["is_proposal"] is True and budget["recurring_expenses"] == 0
    assert basic_service.get_financial_calendar("2026-09")["period"] == "2026-09"


@pytest.mark.parametrize("call", [
    lambda: basic_service.create_recurring_item(SimpleNamespace()),
    lambda: basic_service.update_recurring_item(1, SimpleNamespace()),
    lambda: basic_service.delete_recurring_item(1),
    lambda: basic_service.save_guided_budget(SimpleNamespace(items=[])),
])
def test_basic_writes_refuse_until_the_migration_exists(conn, call):
    with pytest.raises(HTTPException) as error:
        call()

    assert error.value.status_code == 503
    assert not any(table in q for q in conn.queries for table in BASIC if "to_regclass" not in q)
