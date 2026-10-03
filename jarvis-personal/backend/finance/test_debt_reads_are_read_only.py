"""Reading debts never writes: not for Users, not for the Owner.

Applying scheduled installments (record each due installment as paid and move the
debt) is the explicit command `apply_due_installments` (POST
/finance/debts/apply-due-installments, dry run by default). Every read path that
reaches get_debts() or the cycle report leaves debts, payments and the ledger
untouched. The real finance.service code runs against an in-memory store.
Synthetic data only.
"""
import copy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from fastapi import HTTPException

from backend.finance import routes, service
from backend.main import app
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
            if not any((x["workspace_id"], x["debt_id"], x["payment_date"]) == (p[14], p[15], p[16]) for x in payments):
                payments.append({"workspace_id": p[0], "debt_id": p[1], "principal": p[3], "payment_date": p[12], "installment_number": p[13]})
            return _rows([])
        if q.startswith("INSERT INTO transactions"):
            if not any((x["workspace_id"], x["notes"]) == (params[6], params[7]) for x in txs):
                txs.append({"workspace_id": params[0], "type": "debt_payment", "amount": params[3], "notes": params[5]})
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
        "compute_advisor_strategy": lambda **_kw: {}, "list_account_balances": lambda: {"items": []},
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


def _owner_debt_in_a(store):
    """An Owner debt with five installments already due, in the Owner workspace A."""
    store.state["debts"][2]["workspace_id"] = WS_A
    store.state["debts"].pop(1)


def test_owner_reads_never_write(store):
    _owner_debt_in_a(store)
    before = _stored(store, 2)
    token = _as("owner")
    try:
        first, second = service.get_debts(), routes.debts()
    finally:
        reset_current_user(token)
    assert store.writes == []
    assert _stored(store, 2) == before
    assert store.state["payments"] == [] and store.state["transactions"] == []
    assert first == second


def test_the_cycle_report_never_applies_installments(monkeypatch):
    calls, writes = [], []
    monkeypatch.setattr(service, "apply_due_installments", lambda *a, **k: calls.append(1))

    class ReadOnly:
        def __enter__(self): return self
        def __exit__(self, *_a): return False
        def commit(self): writes.append("commit")
        def execute(self, query, params=()):
            if query.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")):
                writes.append(query.split()[0])
            return _rows([])

    monkeypatch.setattr(service, "get_connection", lambda: ReadOnly())
    token = _as("owner")
    try:
        service.get_financial_cycle_report(as_of=TODAY)
    finally:
        reset_current_user(token)
    assert calls == [] and writes == []


def test_dry_run_lists_due_installments_and_writes_nothing(store):
    _owner_debt_in_a(store)
    before = _stored(store, 2)
    token = _as("owner")
    try:
        plan = service.apply_due_installments(dry_run=True)
    finally:
        reset_current_user(token)
    assert plan["dry_run"] is True and len(plan["installments"]) == 5
    assert [i["installment_number"] for i in plan["installments"]] == [1, 2, 3, 4, 5]
    assert all(date.fromisoformat(i["due_date"]) <= TODAY for i in plan["installments"])
    assert plan["debts_to_update"] == [2] and "debts_updated" not in plan
    assert store.writes == [] and _stored(store, 2) == before


def test_the_command_records_each_due_installment_once_and_is_idempotent(store):
    _owner_debt_in_a(store)
    token = _as("owner")
    try:
        planned = service.apply_due_installments(dry_run=True)["installments"]
        first = service.apply_due_installments(dry_run=False)
        writes_after_first = list(store.writes)
        second = service.apply_due_installments(dry_run=False)
    finally:
        reset_current_user(token)
    # The real run records exactly the dry run's plan.
    assert first["installments"] == planned
    assert [p["installment_number"] for p in store.state["payments"]] == [1, 2, 3, 4, 5]
    assert len(store.state["transactions"]) == 5
    debt = _stored(store, 2)
    assert debt["remaining_amount"] == planned[-1]["new_remaining_amount"] < 500000.0
    assert debt["installments_paid"] == 5
    # Running it again changes nothing and writes nothing.
    assert second["installments"] == [] and second["debts_updated"] == []
    assert store.writes == writes_after_first
    assert len(store.state["payments"]) == 5 and len(store.state["transactions"]) == 5


def test_a_partly_recorded_debt_with_a_stale_counter_gets_only_the_missing_installments(store):
    # Installments 1-4 are due (payment day 1), 5 is next month. The ledger already has 1 and 2
    # (with their transactions), the row's balance reflects them, but installments_paid says 1.
    _owner_debt_in_a(store)
    first_due = service._add_months(TODAY.replace(day=1), -3, 1)
    due = [service._add_months(first_due, n, 1).isoformat() for n in range(5)]
    debt = store.state["debts"][2]
    debt.update(payment_day=1, first_payment_date=first_due, installments_paid=1,
                last_payment_date=due[1], remaining_amount=450000.0)
    for number in (1, 2):
        store.state["payments"].append({"workspace_id": WS_A, "debt_id": 2, "principal": 25000.0,
                                        "payment_date": due[number - 1], "installment_number": number})
        store.state["transactions"].append({"workspace_id": WS_A, "type": "debt_payment", "amount": 50000.0,
                                            "notes": f"debt_id:2;installment:{number}"})
    before = _stored(store, 2)
    token = _as("owner")
    try:
        dry = service.apply_due_installments(dry_run=True)
        after_dry = (list(store.writes), _stored(store, 2), len(store.state["payments"]), len(store.state["transactions"]))
        real = service.apply_due_installments(dry_run=False)
        writes_after_real = list(store.writes)
        again = service.apply_due_installments(dry_run=False)
    finally:
        reset_current_user(token)

    # Dry run: writes nothing, plans only the missing due installments 3 and 4, chained on the balance.
    assert after_dry == ([], before, 2, 2)
    assert dry["debts_to_update"] == [2] and "debts_updated" not in dry
    plan = dry["installments"]
    assert [(i["installment_number"], i["due_date"]) for i in plan] == [(3, due[2]), (4, due[3])]
    assert plan[0]["previous_remaining_amount"] == 450000.0
    assert plan[1]["previous_remaining_amount"] == plan[0]["new_remaining_amount"]
    assert all(0 < i["principal"] <= i["amount"] for i in plan)
    assert all(i["new_remaining_amount"] == round(i["previous_remaining_amount"] - i["principal"], 2) for i in plan)
    assert plan[1]["new_remaining_amount"] < plan[0]["new_remaining_amount"] < 450000.0

    # Real run: exactly the plan, nothing duplicated, row brought in line with the ledger.
    assert real["installments"] == plan and real["debts_updated"] == [2] and "debts_to_update" not in real
    assert sorted(p["installment_number"] for p in store.state["payments"]) == [1, 2, 3, 4]
    assert len({p["payment_date"] for p in store.state["payments"]}) == 4
    notes = [t["notes"] for t in store.state["transactions"]]
    assert sorted(notes) == [f"debt_id:2;installment:{n}" for n in (1, 2, 3, 4)]
    stored = _stored(store, 2)
    assert stored["remaining_amount"] == plan[-1]["new_remaining_amount"]
    assert stored["installments_paid"] == 4
    assert stored["last_payment_date"] == due[3] and stored["next_payment_date"] == due[4]

    # A second real run is idempotent: nothing planned, nothing written.
    assert again == {"dry_run": False, "installments": [], "debts_updated": []}
    assert store.writes == writes_after_real and _stored(store, 2) == stored
    assert len(store.state["payments"]) == 4 and len(store.state["transactions"]) == 4


def test_an_installment_not_yet_due_is_never_recorded(store):
    _owner_debt_in_a(store)
    store.state["debts"][2]["first_payment_date"] = TODAY + timedelta(days=20)
    before = _stored(store, 2)
    token = _as("owner")
    try:
        dry = service.apply_due_installments(dry_run=True)
        real = service.apply_due_installments(dry_run=False)
    finally:
        reset_current_user(token)
    assert dry["installments"] == [] and real["installments"] == []
    # Nothing to record: the debt row (updated_at included) is not written.
    assert store.writes == [] and _stored(store, 2) == before


def test_the_command_never_touches_another_workspace(store):
    before_b = _stored(store, 2)  # debt 2 lives in workspace B
    token = _as("owner", WS_A)
    try:
        service.apply_due_installments(dry_run=False)
    finally:
        reset_current_user(token)
    assert _stored(store, 2) == before_b
    assert all(p["workspace_id"] == WS_A for p in store.state["payments"])


def test_only_the_owner_can_run_the_command(store):
    for role in ("user", "admin"):
        token = _as(role)
        try:
            with pytest.raises(HTTPException) as denied:
                service.apply_due_installments(dry_run=False)
        finally:
            reset_current_user(token)
        assert denied.value.status_code == 403
    assert store.writes == []


def test_the_command_route_is_a_dry_run_by_default(store):
    _owner_debt_in_a(store)
    token = _as("owner")
    try:
        result = routes.debts_apply_due_installments()
    finally:
        reset_current_user(token)
    assert result["dry_run"] is True and result["installments"]
    assert store.writes == []
    route = next(r for r in app.routes if getattr(r, "path", "") == "/finance/debts/apply-due-installments")
    assert route.methods == {"POST"}
    assert not any(getattr(r, "path", "") == "/finance/debts/apply-due-installments" and "GET" in r.methods for r in app.routes)


def test_another_workspace_never_affects_the_debt(store):
    before = _stored(store, 1)
    token = _as("owner", WS_B)  # even the Owner of workspace B, reading
    try:
        service.get_debts()
    finally:
        reset_current_user(token)
    assert _stored(store, 1) == before
    assert store.writes == []
    token = _as("user", WS_A)
    try:
        assert [d["id"] for d in service.get_debts()] == [1]
    finally:
        reset_current_user(token)
