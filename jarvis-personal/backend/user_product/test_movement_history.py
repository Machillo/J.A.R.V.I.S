"""The full history (GET /user-product/free/movements) must show movements
confirmed from Gmail for every plan, once, and only for the caller's workspace."""
import re
from types import SimpleNamespace

import pytest

from backend.auth import saas
from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import free_service, gmail_service
from backend.user_product.test_gmail_accept import ALLOWED_USER_ID, FakeDatabase

WORKSPACE, OTHER_WORKSPACE = "workspace-a", "workspace-b"


class HistoryConnection:
    """Evaluates the transactions branch of list_free_movements on the fake DB."""

    def __init__(self, db, queries):
        self.db, self.queries = db, queries

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()), params))
        workspace = params[-1]
        rows = [
            {"movement_id": f"transaction:{row['id']}", "source_id": row["id"], "origin": "transaction",
             "transaction_type": "expense", "editable": False}
            for row in self.db.state["transactions"] if row["workspace_id"] == workspace
        ]
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


@pytest.mark.parametrize("plan", ["free", "basic", "vip"])
def test_full_history_feature_is_available_on_every_plan(plan):
    assert saas.PLAN_RANK[plan] >= saas.PLAN_RANK[saas.BUILTIN_FEATURE_MIN_PLAN["transactions"]]
