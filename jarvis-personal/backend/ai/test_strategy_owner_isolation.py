"""Owner ↔ Users isolation in the strategy and Salvavidas engines (CLAUDE.md §4.A).

The shared VIP strategy dashboard and the Salvavidas used to run the Owner's personal
JARVIS rules for every VIP user: cash found by the name "MultiMoney", Casa/Línea/Liberty
as mandatory bills, his large Popular loan ordered last, his pay cycle (rolls on day 6,
card cut on the 21st), his payroll projection and his Wise/IBKR funding model. Those
rules now run only behind the server-resolved Owner role.

- A normal VIP (and admin) never reaches any Owner input, rule, name or classification.
- The Owner keeps his historical inputs and rules.
Synthetic data only; no database (the engines' loaders are stubbed or answered in memory).
"""
from __future__ import annotations

import inspect
import json
from datetime import date

import pytest

from backend.ai import strategy_dashboard
from backend.auth.current_user import reset_current_user, set_current_user
from backend.finance import emergency_fund

OWNER_LITERALS = ("multimoney", "casa", "línea", "linea", "liberty", "popular", "kenneth", "wise", "ibkr")
OWNER_ONLY_INPUTS = (
    "_fetch_distributable_cash",          # MultiMoney cash
    "_get_strategy_living_expenses",      # Casa / Línea
    "_safe_cycle_report",                 # day-6 cycle, day-21 card cut
    "calculate_monthly_salary_projection",  # employment profile, payroll, bonuses
    "get_financial_summary",
    "_fetch_post_cut_expenses",
    "_pending_mandatory_fixed_expenses",
)
TODAY = date(2026, 9, 15)


def _as(role, fn, *args, **kwargs):
    token = set_current_user({"id": 7, "account_id": "acc-test", "workspace_id": "ws-test", "role": role})
    try:
        return fn(*args, **kwargs)
    finally:
        reset_current_user(token)


def _users_inputs(income=900000, spending=200000, debt_paid=0, pending=None, recurring=150000):
    return {
        "income_policy": {"policy": "income-policy-v1", "source": "declared", "declared": income,
                          "baseline": income, "recurring": 0, "monthly_income": income},
        "month": {"income": income, "expenses": spending, "debt_paid": debt_paid},
        "period": {"start": "2026-09-01", "end": "2026-09-30"},
        "recurring_expense_monthly": recurring,
        "pending_recurring": pending if pending is not None else [{"id": 1, "name": "Alquiler", "due_day": 28, "amount": 100000}],
    }


DEBTS = [
    # The user's own debt names are the user's data; only the Owner's ordering rule must not apply.
    {"id": 1, "name": "Préstamo Banco Popular", "remaining_amount": 2_000_000, "total_amount": 2_500_000,
     "monthly_payment": 80000, "interest_rate": 30, "debt_type": "loan"},
    {"id": 2, "name": "Tarjeta Sintética", "remaining_amount": 500_000, "total_amount": 600_000,
     "monthly_payment": 30000, "interest_rate": 20, "debt_type": "credit_card"},
]


@pytest.fixture
def users_engine(monkeypatch):
    """The Users path with every Owner-only input wired to fail if it is ever reached."""
    for name in OWNER_ONLY_INPUTS:
        monkeypatch.setattr(strategy_dashboard, name,
                            lambda *_a, _n=name, **_k: (_ for _ in ()).throw(AssertionError(f"Users strategy read {_n}")))
    monkeypatch.setattr(strategy_dashboard, "get_debts", lambda: [dict(d) for d in DEBTS])
    monkeypatch.setattr(strategy_dashboard, "_load_users_strategy_inputs", lambda *_a: _users_inputs())
    monkeypatch.setattr(strategy_dashboard, "get_salvavidas_state",
                        lambda: {"scope": "users", "current_amount": None, "monthly_base": 260000})
    monkeypatch.setattr(strategy_dashboard, "_fetch_active_financial_goals", lambda *_a: [])
    monkeypatch.setattr(strategy_dashboard, "_fetch_investment_portfolio",
                        lambda workspace_id, owner=False: {"market_value": 0, **({"funding_model": {}} if owner else {})})
    return monkeypatch


@pytest.mark.parametrize("role", ["user", "admin"])
def test_a_vip_user_or_admin_never_reaches_an_owner_input(users_engine, role):
    result = _as(role, strategy_dashboard.build_local_strategy_blueprint)
    assert result["scope"] == "users"
    assert result["distributable_account_cash"] is None  # no MultiMoney cash, no invented balance
    assert "funding_model" not in result["investment_portfolio"]  # no Wise/IBKR route
    for debug in ("living_expense_debug", "salary_projection_debug", "cycle_report_debug", "mandatory_fixed_pending_items"):
        assert debug not in result


def test_a_vip_user_gets_no_owner_rule_name_or_classification_in_the_answer(users_engine):
    result = _as("user", strategy_dashboard.build_local_strategy_blueprint)
    # The user's own debt names come back as data; everything DINCR writes is neutral.
    written = json.dumps({k: v for k, v in result.items() if k not in {"timeline", "base_timeline", "primary_debt_name"}},
                         ensure_ascii=False).lower()
    for literal in OWNER_LITERALS:
        assert literal not in written.replace("préstamo banco popular", ""), literal
    assert all("casa" not in rule.lower() and "línea" not in rule.lower() for rule in result["rules"])


def test_a_vip_users_debt_order_follows_cost_not_the_owners_popular_rule(users_engine):
    users = _as("user", strategy_dashboard.build_local_strategy_blueprint)
    assert [item["name"] for item in users["timeline"]][0] == "Préstamo Banco Popular"  # 30% beats 20%
    owner_order = strategy_dashboard._sort_debts_for_director([dict(d) for d in DEBTS], owner_rules=True)
    assert [d["name"] for d in owner_order][-1] == "Préstamo Banco Popular"  # the Owner's rule, Owner only


def test_the_users_surplus_is_the_month_after_spending_debts_and_pending_recurring(users_engine):
    result = _as("user", strategy_dashboard.build_local_strategy_blueprint)
    formula = result["distribution_formula"]
    # 900k income − 200k recorded − 110k debt payments still due − 100k rent due later = 490k.
    assert (formula["income"], formula["recorded_spending"], formula["debt_commitment"], formula["pending_recurring"]) == (
        900000, 200000, 110000, 100000)
    assert formula["surplus"] == 490000 and result["allocation_total"] == 490000
    assert set(formula) == {"income", "recorded_spending", "debt_commitment", "pending_recurring", "surplus", "deficit"}


def test_unknown_savings_are_never_reported_as_zero_in_the_users_strategy(users_engine):
    result = _as("user", strategy_dashboard.build_local_strategy_blueprint)  # salvavidas current_amount: None
    emergency = result["emergency_fund"]
    assert emergency["current"] is None and emergency["current_known"] is False and emergency["level"] == "unknown"
    users_engine.setattr(strategy_dashboard, "get_salvavidas_state",
                         lambda: {"scope": "users", "current_amount": 300000, "monthly_base": 260000})
    known = _as("user", strategy_dashboard.build_local_strategy_blueprint)["emergency_fund"]
    assert known["current"] == 300000 and known["current_known"] is True


def test_a_users_strategy_without_income_says_so_instead_of_planning_zero(users_engine):
    users_engine.setattr(strategy_dashboard, "_load_users_strategy_inputs", lambda *_a: _users_inputs(income=0))
    result = _as("user", strategy_dashboard.build_local_strategy_blueprint)
    assert result["status"] == "needs_income" and result["allocation_total"] == 0


def test_the_owner_keeps_his_historical_inputs_and_rules(monkeypatch):
    calls = []

    def record(name, value):
        def fn(*_a, **_k):
            calls.append(name)
            return value
        return fn

    monkeypatch.setattr(strategy_dashboard, "get_debts", lambda: [dict(d) for d in DEBTS])
    monkeypatch.setattr(strategy_dashboard, "get_financial_summary", record("summary", {}))
    monkeypatch.setattr(strategy_dashboard, "calculate_monthly_salary_projection",
                        record("payroll", {"results": {"base_net": 1_200_000, "projected_net": 1_350_000}}))
    monkeypatch.setattr(strategy_dashboard, "_safe_cycle_report",
                        record("cycle", {"income": {"expected_total": 1_350_000, "received_from_transactions": 0}}))
    monkeypatch.setattr(strategy_dashboard, "_get_strategy_living_expenses", record("casa_linea", {"fixed_living_total": 150000}))
    monkeypatch.setattr(strategy_dashboard, "get_salvavidas_state", record("salvavidas", {"current_amount": 0, "monthly_base": 0}))
    monkeypatch.setattr(strategy_dashboard, "_fetch_post_cut_expenses", record("post_cut", {"total": 0}))
    monkeypatch.setattr(strategy_dashboard, "_pending_mandatory_fixed_expenses", record("mandatory", {"total": 0}))
    monkeypatch.setattr(strategy_dashboard, "_fetch_distributable_cash", record("multimoney", 300000.0))
    monkeypatch.setattr(strategy_dashboard, "_fetch_active_financial_goals", lambda *_a: [])
    monkeypatch.setattr(strategy_dashboard, "_fetch_investment_portfolio",
                        lambda workspace_id, owner=False: {"funding_model": {"wise": 1}} if owner else {})
    monkeypatch.setattr(strategy_dashboard, "_load_users_strategy_inputs",
                        lambda *_a: (_ for _ in ()).throw(AssertionError("the Owner never uses the Users inputs")))

    result = _as("owner", strategy_dashboard.build_local_strategy_blueprint)
    assert result["scope"] == "owner"
    assert {"payroll", "cycle", "casa_linea", "multimoney", "post_cut", "mandatory"} <= set(calls)
    assert result["recurring_monthly_income"] == 1_200_000 and result["current_month_extra_net"] == 150_000  # OT/bonus
    assert result["distributable_account_cash"] == 300000 and result["investment_portfolio"] == {"funding_model": {"wise": 1}}
    assert result["income_policy"] is None
    assert any("Casa" in rule for rule in result["rules"])
    assert [item["name"] for item in result["timeline"]][-1] == "Préstamo Banco Popular"


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_the_wise_ibkr_funding_model_is_only_the_owners(monkeypatch):
    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, query, params=()):
            return _Rows([{"total": 0}]) if "SUM" in query else _Rows([])

    monkeypatch.setattr(strategy_dashboard, "get_connection", lambda: Conn())
    assert "funding_model" not in strategy_dashboard._fetch_investment_portfolio("ws-test")
    assert "funding_model" in strategy_dashboard._fetch_investment_portfolio("ws-test", True)


@pytest.mark.parametrize("function", [
    strategy_dashboard._users_strategy_blueprint,
    strategy_dashboard._users_blueprint_from_inputs,
    strategy_dashboard._load_users_strategy_inputs,
    emergency_fund._users_salvavidas_state,
    emergency_fund._users_salvavidas_from,
    emergency_fund._load_users_obligations,
    emergency_fund._update_users_salvavidas,
])
def test_the_users_paths_carry_no_owner_literal_table_or_cycle(function):
    source = inspect.getsource(function).lower()
    for literal in (*OWNER_LITERALS, "fixed_expenses", "cycle_report", "salary_projection", "account_balances"):
        assert literal not in source, (function.__name__, literal)


# Salvavidas ---------------------------------------------------------------------------------

class _ObligationsConn:
    """Answers the Users Salvavidas queries; the Owner's fixed_expenses must never be asked."""

    def __init__(self, state):
        self.state = state
        self.recurring, self.savings = state["recurring"], state["savings"]

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, query, params=()):
        q = " ".join(query.split())
        assert "fixed_expenses" not in q, "Users Salvavidas read the Owner's fixed_expenses"
        if "to_regclass" in q:
            return _Rows([{"missing": None}])
        if "FROM finva_recurring_items" in q:
            return _Rows([dict(r) for r in self.recurring])
        if q.startswith("UPDATE financial_profiles SET liquid_savings=%s"):
            if self.savings is False:
                return _Rows([])
            self.state["savings"] = float(params[0])
            self.state["writes"].append(params)
            return _Rows([{"account_id": params[1]}])
        if "FROM financial_profiles" in q:
            return _Rows([] if self.savings is False else [{"liquid_savings": self.savings}])
        if "FROM debts" in q:
            return _Rows([{"id": 2, "name": "Tarjeta Sintética", "debt_type": "credit_card", "remaining_amount": 500000,
                           "monthly_payment": 30000, "payment_day": 5}])
        raise AssertionError(q[:80])


RECURRING = [
    # A user may call a bill "Casa" or "Liberty"; it is an ordinary obligation, never an Owner classification.
    {"id": 1, "name": "Casa", "amount": 200000, "category": "Vivienda", "frequency": "monthly", "due_day": 1},
    {"id": 2, "name": "Liberty línea", "amount": 15000, "category": "Teléfono", "frequency": "monthly", "due_day": 10},
    {"id": 3, "name": "Seguro anual", "amount": 120000, "category": "Seguros", "frequency": "annual", "due_day": 3},
]


@pytest.fixture
def salvavidas_db(monkeypatch):
    state = {"recurring": RECURRING, "savings": 490000.0, "prefs": {}, "writes": []}
    monkeypatch.setattr(emergency_fund, "get_connection", lambda: _ObligationsConn(state))
    monkeypatch.setattr(emergency_fund, "get_preference", lambda key, default=None: state["prefs"].get(key, default))
    monkeypatch.setattr(emergency_fund, "set_preference", lambda key, value: state["prefs"].__setitem__(key, value))
    return state


def test_users_salvavidas_is_months_of_their_real_obligations(salvavidas_db):
    state = _as("user", emergency_fund.get_salvavidas_state)
    assert state["scope"] == "users" and state["status"] == "OK"
    # 30k debt + 200k + 15k + 120k/12 = 255k a month; 6 months by default.
    assert state["monthly_base"] == 255000 and state["target_months"] == 6 and state["target_amount"] == 1530000
    assert state["current_amount"] == 490000 and state["coverage_months"] == round(490000 / 255000, 2)
    assert "mandatory_expenses" not in state and "available_expenses" not in state
    assert {item["name"] for item in state["obligations"]} == {"Casa", "Liberty línea", "Seguro anual"}
    assert [m["months"] for m in state["milestones"]] == [1, 3, 6] and state["milestones"][0]["reached"] is True


def test_unknown_savings_stay_unknown_never_zero_coverage(salvavidas_db):
    salvavidas_db["savings"] = None
    state = _as("user", emergency_fund.get_salvavidas_state)
    assert state["current_amount"] is None and state["current_amount_known"] is False
    assert state["coverage_months"] is None and state["progress_percent"] is None and state["missing_amount"] is None


def test_without_obligations_the_users_salvavidas_asks_for_them(salvavidas_db, monkeypatch):
    salvavidas_db["recurring"] = []
    monkeypatch.setattr(emergency_fund, "_fetch_active_debts", lambda _ws: [])
    state = _as("user", emergency_fund.get_salvavidas_state)
    assert state["status"] == "needs_obligations" and state["monthly_base"] == 0 and state["coverage_months"] is None


def test_users_update_their_goal_and_declared_savings_never_an_owner_account(salvavidas_db, monkeypatch):
    from backend.finance import intelligence
    monkeypatch.setattr(intelligence, "upsert_account_balance",
                        lambda **_k: (_ for _ in ()).throw(AssertionError("Users Salvavidas wrote an account")))
    assert _as("user", emergency_fund.update_salvavidas, target_months=3)["target_months"] == 3
    # The historical screen saves amount + target + an empty protected list together: it keeps working.
    state = _as("user", emergency_fund.update_salvavidas, current_amount=600000, protected_expense_ids=[], target_months=1)
    assert state["current_amount"] == 600000 and state["target_months"] == 1
    assert salvavidas_db["writes"] == [(600000.0, "acc-test", "ws-test")]  # financial_profiles, this account only
    with pytest.raises(ValueError):
        _as("user", emergency_fund.update_salvavidas, protected_expense_ids=[1])  # no Owner picker for Users
    with pytest.raises(ValueError):
        _as("user", emergency_fund.update_salvavidas, target_months=4)
    with pytest.raises(ValueError):
        _as("user", emergency_fund.update_salvavidas, current_amount=-1)


def test_users_without_a_financial_situation_cannot_save_savings(salvavidas_db):
    salvavidas_db["savings"] = False  # no financial_profiles row
    with pytest.raises(ValueError):
        _as("user", emergency_fund.update_salvavidas, current_amount=1000)
    assert salvavidas_db["writes"] == []


class _OwnerConn:
    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, query, params=()):
        q = " ".join(query.split())
        if "FROM debts" in q:
            return _Rows([])
        if "FROM fixed_expenses" in q:
            return _Rows([{"id": 10, "name": "Casa", "category": "Vivienda", "expected_amount": 200000, "currency": "CRC",
                           "frequency": "monthly", "interval_months": 1, "due_day": 1, "is_active": True,
                           "payment_method": None, "aliases": []},
                          {"id": 11, "name": "Gimnasio", "category": "Salud", "expected_amount": 20000, "currency": "CRC",
                           "frequency": "monthly", "interval_months": 1, "due_day": 5, "is_active": True,
                           "payment_method": None, "aliases": []}])
        if "to_regclass('public.account_balances')" in q:
            return _Rows([{"table_name": None}])
        raise AssertionError(q[:80])


def test_the_owner_keeps_his_historical_salvavidas(monkeypatch):
    from backend.finance import intelligence
    written = []
    monkeypatch.setattr(emergency_fund, "get_connection", lambda: _OwnerConn())
    monkeypatch.setattr(emergency_fund, "get_preference", lambda key, default=None: {"current_amount": 50000})
    monkeypatch.setattr(emergency_fund, "set_preference", lambda key, value: None)
    monkeypatch.setattr(intelligence, "upsert_account_balance", lambda **kwargs: written.append(kwargs))
    state = _as("owner", emergency_fund.get_salvavidas_state)
    assert state["scope"] == "owner"
    assert [item["name"] for item in state["mandatory_expenses"]] == ["Casa"]  # his Casa/Línea rule
    assert [item["name"] for item in state["available_expenses"]] == ["Gimnasio"]
    _as("owner", emergency_fund.update_salvavidas, current_amount=75000)
    assert written and written[0]["bank_name"] == "MultiMoney" and written[0]["account_type"] == "emergency_fund"


def test_the_users_salvavidas_route_answers_422_for_an_owner_only_field(monkeypatch):
    from fastapi import HTTPException

    from backend.user_product import routes
    from backend.finance.models import SalvavidasUpdateRequest
    monkeypatch.setattr(routes, "require_feature", lambda _feature: None)
    monkeypatch.setattr(routes, "update_salvavidas", lambda **_k: (_ for _ in ()).throw(ValueError("Tus ahorros…")))
    with pytest.raises(HTTPException) as error:
        routes.vip_salvavidas_update(SalvavidasUpdateRequest(current_amount=10))
    assert error.value.status_code == 422


def test_the_owner_boundary_is_the_server_role_only():
    assert _as("owner", strategy_dashboard._is_owner) and _as("owner", emergency_fund._is_owner)
    for role in ("user", "admin", None):
        assert not _as(role, strategy_dashboard._is_owner) and not _as(role, emergency_fund._is_owner)
