"""Reading Home/Strategy must never rewrite user-owned debt data.

The automatic installment sync (record each due installment as paid and rewrite
the debt) is a DINCR Owner automation. DINCR Users never opt in, so every read
path that reaches get_debts() must leave their debts, payments and ledger
untouched. The real finance.service code runs against an in-memory store.
Synthetic data only.
"""
import copy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.finance import service
from backend.financial_lifecycle import state as lifecycle_state

WS_A, WS_B = "workspace-a", "workspace-b"
TODAY = date.today()
CREATED = TODAY - timedelta(days=150)  # five due installments by now


def _debt(debt_id, workspace):
    # Exactly what DINCR Users create_user_debt stores.
    return {
        "id": debt_id, "workspace_id": workspace, "user_id": 90, "name": "Tarjeta Sintética",
        "debt_type": "credit_card", "total_amount": 600000.0, "remaining_amount": 500000.0,
        "monthly_payment": 50000.0, "interest_rate": 30.0, "term_months": 24, "payment_day": 15,
        "start_date": None, "first_payment_date": None, "next_payment_date": TODAY + timedelta(days=9),
        "last_payment_date": None, "auto_update_monthly": True, "installments_paid": 0,
        "interest_method": "monthly", "fixed_fee_amount": 0, "created_at": CREATED, "updated_at": CREATED,
    }


class Store:
    def __init__(self):
        self.state = {"debts": {1: _debt(1, WS_A), 2: _debt(2, WS_B)}, "payments": [], "transactions": []}
        self.writes = []

    def connect(self):
        return Conn(self)


def _rows(rows):
    rows = [dict(r) for r in rows]
    return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)


class Conn:
    def __init__(self, store):
        self.store, self.work = store, copy.deepcopy(store.state)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.store.state = copy.deepcopy(self.work)

    def execute(self, query, params=()):
        q = " ".join(query.split())
        debts, payments, txs = self.work["debts"], self.work["payments"], self.work["transactions"]
        if q.startswith(("UPDATE", "INSERT", "DELETE")):
            self.store.writes.append(q[:60])
        if q.startswith("SELECT id, name, debt_type, total_amount, remaining_amount, monthly_payment, interest_rate, term_months, payment_day, start_date, first_payment_date, auto_update_monthly"):
            return _rows(d for d in debts.values() if d["workspace_id"] == params[0]
                         and d["auto_update_monthly"] is not False and d["remaining_amount"] > 0)
        if q.startswith("SELECT payment_date, installment_number FROM debt_payments"):
            return _rows(p for p in payments if (p["workspace_id"], p["debt_id"]) == params)
        if q.startswith("INSERT INTO debt_payments"):
            p = params
            if not any((x["workspace_id"], x["debt_id"], x["payment_date"]) == (p[15], p[16], p[17]) for x in payments):
                payments.append({"workspace_id": p[1], "debt_id": p[2], "principal": p[4], "payment_date": p[13], "installment_number": p[14]})
            return _rows([])
        if q.startswith("INSERT INTO transactions"):
            txs.append({"workspace_id": params[1], "type": "debt_payment", "amount": params[4]})
            return _rows([])
        if q.startswith("UPDATE debts SET start_date"):
            start, first, balance, paid, last, nxt, finished, debt_id, workspace = params
            d = debts[debt_id]
            assert d["workspace_id"] == workspace
            d.update(start_date=d["start_date"] or start, first_payment_date=d["first_payment_date"] or first,
                     remaining_amount=balance, installments_paid=paid, last_payment_date=last, next_payment_date=nxt)
            return _rows([])
        if "FROM debts WHERE workspace_id = %s ORDER BY id DESC" in q:
            return _rows(d for d in debts.values() if d["workspace_id"] == params[0])
        if "FROM debt_payments WHERE workspace_id = %s GROUP BY debt_id" in q:
            stats = {}
            for p in payments:
                if p["workspace_id"] == params[0]:
                    s = stats.setdefault(p["debt_id"], {"debt_id": p["debt_id"], "monthly_count": 0, "max_installment": 0, "last_payment_date": None})
                    s["monthly_count"] += 1
                    s["max_installment"] = max(s["max_installment"], p["installment_number"])
                    s["last_payment_date"] = p["payment_date"]
            return _rows(stats.values())
        raise AssertionError(f"Unexpected query: {q[:100]}")


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(service, "get_connection", s.connect)
    return s


def _as(role, workspace=WS_A):
    return set_current_user({"id": 12, "account_id": f"account-{workspace}", "workspace_id": workspace, "role": role})


def _stored(store, debt_id=1):
    return dict(store.state["debts"][debt_id])


def test_loading_home_once_does_not_alter_user_debt(store):
    before = _stored(store)
    token = _as("user")
    try:
        debts = service.get_debts()
    finally:
        reset_current_user(token)
    assert store.writes == []
    assert _stored(store) == before
    assert store.state["payments"] == [] and store.state["transactions"] == []
    assert [d["remaining_amount"] for d in debts] == [500000.0]


def test_loading_home_repeatedly_is_idempotent(store):
    before = _stored(store)
    token = _as("user")
    try:
        results = [[d["remaining_amount"] for d in service.get_debts()] for _ in range(5)]
    finally:
        reset_current_user(token)
    assert results == [[500000.0]] * 5
    assert store.writes == [] and _stored(store) == before


def test_imported_transactions_then_home_keep_the_debt_in_context(store, monkeypatch):
    """Bank-email imports exist and Home builds the financial state (proactive advisor path)."""
    store.state["transactions"] += [
        {"workspace_id": WS_A, "type": "income", "amount": 18500, "source": "finva_gmail"},
        {"workspace_id": WS_A, "type": "debt_payment", "amount": 50000, "source": "finva_gmail"},
    ]
    for name, value in {
        "build_advisor_strategy": lambda **_kw: {}, "list_account_balances": lambda: {"items": []},
        "get_salvavidas_state": lambda: {}, "get_real_availability": lambda: {},
        "get_financial_deterioration": lambda: {}, "get_monthly_financial_flow": lambda: {"months": []},
    }.items():
        monkeypatch.setattr(lifecycle_state, name, value)
    before = _stored(store)
    token = _as("user")
    try:
        states = [lifecycle_state.build_financial_state() for _ in range(3)]
    finally:
        reset_current_user(token)
    assert store.writes == [] and _stored(store) == before
    for current in states:
        assert current["debt"]["active_count"] == 1
        assert current["debt"]["total"] == 500000.0
        assert current["debt"]["monthly_payments"] == 50000.0


def test_another_workspace_never_affects_the_debt(store):
    before = _stored(store, 1)
    token = _as("owner", WS_B)  # even the Owner automation of workspace B
    try:
        service.get_debts()
    finally:
        reset_current_user(token)
    assert _stored(store, 1) == before
    assert all(p["workspace_id"] == WS_B for p in store.state["payments"])
    token = _as("user", WS_A)
    try:
        assert [d["id"] for d in service.get_debts()] == [1]
    finally:
        reset_current_user(token)


def test_without_an_authenticated_context_nothing_is_written(store):
    service._sync_automatic_debt_payments(90, WS_A)
    assert store.writes == []


def test_owner_schedule_automation_is_preserved_and_idempotent(store):
    """The Owner still gets due installments applied once each."""
    store.state["debts"][2]["workspace_id"] = WS_A  # an Owner debt in the Owner workspace
    store.state["debts"].pop(1)
    token = _as("owner")
    try:
        first = service.get_debts()
        second = service.get_debts()
    finally:
        reset_current_user(token)
    installments = [p["installment_number"] for p in store.state["payments"]]
    assert installments and installments == sorted(set(installments))  # once each
    assert first[0]["remaining_amount"] < 500000.0
    assert second[0]["remaining_amount"] == first[0]["remaining_amount"]
