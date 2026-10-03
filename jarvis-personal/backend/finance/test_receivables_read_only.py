"""The native Owner app reads receivables without changing them (CLAUDE.md §4.C).

GET /finance/receivables (the JARVIS web view) backfills entries, syncs card
charges and income payments, and stores recalculated totals. The native app
reads GET /finance/receivables/view instead: the same list and figures, with no
write and no commit. Synthetic data only.
"""
import re
from datetime import date
from types import SimpleNamespace

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.finance import intelligence

WS = "workspace-owner"
WRITE = re.compile(r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s", re.I)
RECEIVABLE = {
    "id": 7, "person_name": "Persona Sintética", "original_amount": 0, "paid_amount": 0, "pending_amount": 0,
    "status": "pending", "notes": None, "source_type": "manual", "source_key": None,
    "created_at": "2026-01-01", "updated_at": "2026-01-01", "workspace_id": WS,
}


def _rows(rows):
    rows = [dict(r) for r in rows]
    return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)


class Conn:
    """Answers the list's reads; records every statement and commit."""

    def __init__(self):
        self.statements, self.commits = [], 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.commits += 1

    def execute(self, query, params=()):
        self.statements.append(" ".join(query.split()))
        if WRITE.match(query):
            return _rows([{**RECEIVABLE, "original_amount": 3000.0, "paid_amount": 1000.0,
                           "pending_amount": 2000.0, "status": "partial"}])
        if "FROM receivables" in query:
            return _rows([RECEIVABLE])
        if "AS charged" in query:
            return _rows([{"charged": 3000.0, "paid": 1000.0}])
        if "AS prior_charges" in query:
            return _rows([{"prior_charges": 3000.0, "prior_payments": 1000.0, "cycle_charges": 0, "cycle_payments": 0}])
        if "FROM receivable_entries" in query:
            return _rows([{"id": 1, "entry_type": "charge", "amount": 3000.0, "description": "Préstamo",
                           "entry_date": date(2026, 1, 5), "source_type": "manual", "source_key": None,
                           "source_transaction_id": None, "created_at": "2026-01-05", "cycle_start": None, "cycle_end": None}])
        return _rows([])


@pytest.fixture
def conn(monkeypatch):
    connection = Conn()
    monkeypatch.setattr(intelligence, "get_connection", lambda: connection)
    token = set_current_user({"id": 41, "account_id": "account-owner", "workspace_id": WS, "role": "owner"})
    yield connection
    reset_current_user(token)


def test_the_native_view_never_writes_or_commits(conn, monkeypatch):
    def sync(*_args):
        raise AssertionError("the read view must not sync receivables")

    for name in ("_backfill_receivable_entries", "_sync_auto_additional_card_receivables",
                 "_sync_receivable_payments_from_income"):
        monkeypatch.setattr(intelligence, name, sync)

    result = intelligence.read_receivables()

    assert [s for s in conn.statements if WRITE.match(s)] == []
    assert conn.commits == 0
    assert all(s.startswith("SELECT") for s in conn.statements)
    item = result["items"][0]
    assert item["person_name"] == "Persona Sintética"
    assert item["current_amount_due"] == 2000.0
    assert result["summary"]["total_pending"] == 2000.0
    assert result["summary"]["people_count"] == 1


def test_the_view_shows_what_the_web_list_shows(monkeypatch):
    calls = []
    for name in ("_backfill_receivable_entries", "_sync_auto_additional_card_receivables",
                 "_sync_receivable_payments_from_income"):
        monkeypatch.setattr(intelligence, name, lambda *_a, _n=name: calls.append(_n))
    token = set_current_user({"id": 41, "account_id": "account-owner", "workspace_id": WS, "role": "owner"})
    try:
        web, native = Conn(), Conn()
        monkeypatch.setattr(intelligence, "get_connection", lambda: web)
        listed = intelligence.list_receivables()
        monkeypatch.setattr(intelligence, "get_connection", lambda: native)
        viewed = intelligence.read_receivables()
    finally:
        reset_current_user(token)

    # The web list keeps its syncs, its stored recalculation and its commit.
    assert len(calls) == 3
    assert any(s.startswith("UPDATE receivables") for s in web.statements)
    assert web.commits == 1
    assert viewed == listed


def test_the_view_is_an_internal_owner_route():
    from backend.main import app

    route = next(r for r in app.routes if getattr(r, "path", "") == "/finance/receivables/view")
    assert route.methods == {"GET"}
    assert route.dependant.dependencies, "mounted behind INTERNAL_ONLY like the other /finance routes"
