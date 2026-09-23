"""The full history (GET /user-product/free/movements) must show movements
confirmed from Gmail for every plan, once, and only for the caller's workspace."""
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.auth import saas
from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import free_service, gmail_service
from backend.user_product.test_gmail_accept import ALLOWED_USER_ID, FakeDatabase

WORKSPACE, OTHER_WORKSPACE = "workspace-a", "workspace-b"


class HistoryConnection:
    """Evaluates the four union branches against the acceptance flow's fake DB."""

    def __init__(self, db, queries):
        self.db, self.queries = db, queries

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()), params))
        workspace = params[-1]
        rows = []
        for table, origin, kind in (("salaries", "salary", "income"), ("expenses", "expense", "expense"),
                                    ("payroll_events", "payroll", "income")):
            for row in self.db.state.get(table, []):
                if row["workspace_id"] != workspace or (origin == "payroll" and row["amount"] <= 0):
                    continue
                rows.append({"movement_id": f"{origin}:{row['id']}", "source_id": row["id"],
                             "origin": origin, "transaction_type": kind, "editable": True})
        for row in self.db.state["transactions"]:
            if row["workspace_id"] != workspace or row.get("transaction_type") == "internal_transfer":
                continue
            rows.append({"movement_id": f"transaction:{row['id']}", "source_id": row["id"],
                         "origin": "transaction", "transaction_type": row.get("transaction_type", "expense"),
                         "editable": row.get("source", "finva_gmail") in ("finva", "manual", "manual_expense")})
        return SimpleNamespace(fetchall=lambda: rows)


def _as(account, workspace):
    return set_current_user({"id": ALLOWED_USER_ID, "account_id": account, "workspace_id": workspace, "role": "user"})


@pytest.fixture
def db(monkeypatch):
    database = FakeDatabase()
    # A second workspace with its own confirmed-by-email movement.
    database.state["transactions"].append({"id": 4000, "user_id": 99, "workspace_id": OTHER_WORKSPACE})
    monkeypatch.setattr(gmail_service, "get_connection", database.connect)
    return database


def test_accepted_gmail_movement_appears_once_in_history_of_its_workspace_only(db, monkeypatch):
    queries = []
    monkeypatch.setattr(free_service, "get_connection", lambda: HistoryConnection(db, queries))
    token = _as("account-a", WORKSPACE)
    try:
        accepted = gmail_service.review_gmail_candidate(81, "accept")
        gmail_service.review_gmail_candidate(81, "accept")  # a retry must not add a second row
        history = free_service.list_free_movements()
    finally:
        reset_current_user(token)

    ids = [row["movement_id"] for row in history]
    assert ids == [f"transaction:{accepted['transaction_id']}"]
    assert "transaction:4000" not in ids


def test_history_query_scopes_every_source_to_the_current_workspace(db, monkeypatch):
    queries = []
    monkeypatch.setattr(free_service, "get_connection", lambda: HistoryConnection(db, queries))
    token = _as("account-a", WORKSPACE)
    try:
        free_service.list_free_movements()
    finally:
        reset_current_user(token)

    query, params = queries[0]
    branches = query.count("UNION ALL") + 1
    assert branches == 4
    assert len(re.findall(r"WHERE workspace_id=%s", query)) == branches
    assert params == (WORKSPACE,) * branches
    # Internal transfers are not income or expense; bank-confirmed rows are read-only here.
    assert "transaction_type<>'internal_transfer'" in query
    assert "(source IN ('finva','manual','manual_expense'))" in query


def test_main_movement_dataset_keeps_manual_payroll_gmail_and_statement_once(db, monkeypatch):
    db.state["salaries"] = [{"id": 1, "workspace_id": WORKSPACE}, {"id": 2, "workspace_id": OTHER_WORKSPACE}]
    db.state["expenses"] = [{"id": 3, "workspace_id": WORKSPACE}]
    db.state["payroll_events"] = [{"id": 4, "workspace_id": WORKSPACE, "amount": 10}]
    db.state["transactions"].append({"id": 6000, "workspace_id": WORKSPACE, "source": "finva_statement"})
    monkeypatch.setattr(free_service, "get_connection", lambda: HistoryConnection(db, []))
    token = _as("account-a", WORKSPACE)
    try:
        accepted = gmail_service.review_gmail_candidate(81, "accept")
        gmail_service.review_gmail_candidate(81, "accept")
        rows = free_service.list_free_movements()
    finally:
        reset_current_user(token)
    ids = [row["movement_id"] for row in rows]
    assert set(ids) == {"salary:1", "expense:3", "payroll:4", "transaction:6000", f"transaction:{accepted['transaction_id']}"}
    assert len(ids) == len(set(ids)) == 5
    assert "salary:2" not in ids and "transaction:4000" not in ids
    assert all(row["editable"] for row in rows if row["origin"] != "transaction")
    assert all(not row["editable"] for row in rows if row["origin"] == "transaction")


def test_confirmed_own_transfer_is_never_listed_as_income_or_expense(db, monkeypatch):
    db.state["candidates"][81]["is_internal_transfer"] = True
    db.state["transactions"].append({"id": 6001, "workspace_id": WORKSPACE, "transaction_type": "internal_transfer"})
    monkeypatch.setattr(free_service, "get_connection", lambda: HistoryConnection(db, []))
    token = _as("account-a", WORKSPACE)
    try:
        accepted = gmail_service.review_gmail_candidate(81, "accept")
        rows = free_service.list_free_movements()
    finally:
        reset_current_user(token)
    assert accepted["transaction_id"] is None
    assert rows == []


def test_automatic_transaction_cannot_be_edited(db, monkeypatch):
    queries = []

    class NoEditableRow(HistoryConnection):
        def execute(self, query, params=()):
            queries.append((" ".join(query.split()), params))
            return SimpleNamespace(fetchone=lambda: None)

    monkeypatch.setattr(free_service, "get_connection", lambda: NoEditableRow(db, []))
    token = _as("account-a", WORKSPACE)
    try:
        with pytest.raises(HTTPException) as error:
            free_service.update_free_movement("transaction:6000", SimpleNamespace(
                transaction_date="2026-09-20", description="n/a", amount=1, transaction_type="expense",
                category="Otros", notes=""))
    finally:
        reset_current_user(token)
    assert error.value.status_code == 404
    assert "source IN ('finva','manual','manual_expense')" in queries[0][0]
    assert queries[0][1][-1] == WORKSPACE


@pytest.mark.parametrize("plan", ["free", "basic", "vip"])
def test_full_history_feature_is_available_on_every_plan(plan):
    assert saas.PLAN_RANK[plan] >= saas.PLAN_RANK[saas.BUILTIN_FEATURE_MIN_PLAN["transactions"]]
