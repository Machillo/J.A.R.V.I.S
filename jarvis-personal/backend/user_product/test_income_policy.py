"""Income-source precedence policy v1 (income_policy.py) and Home/Strategy consistency.

Synthetic data only. Scenarios A-J from the hardening request.
"""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.ai import strategy_dashboard
from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import gmail_service, income_policy, vip_service
from backend.user_product.test_mail_preserves_financial_state import ACCOUNT, WORKSPACE, LedgerDB, _sync_discovers_accounts

TODAY = date(2026, 9, 24)
DECLARED = {"income_type": "fixed", "fixed_monthly_salary": 1000000}


def _months(values):
    """values: newest last; pads to 12 months."""
    padded = [0] * (12 - len(values)) + list(values)
    start = date(2025, 10, 1)
    return [{"month": f"{(start.year * 12 + start.month - 1 + i) // 12}-{(start.month - 1 + i) % 12 + 1:02d}", "income": v}
            for i, v in enumerate(padded)]


def _imported(months, values):
    padded = [0] * (12 - len(values)) + list(values)
    return {row["month"]: v for row, v in zip(months, padded) if v}


def baseline(profile, recorded, imported=(), recurring=None):
    months = _months(recorded)
    return income_policy.income_baseline(profile, months, _imported(months, imported), recurring)


def test_a_declared_income_without_imports():
    result = baseline(DECLARED, [])
    assert (result["baseline"], result["source"]) == (1000000, "declared")


@pytest.mark.parametrize("partial", [[300000, 250000], [18500], [0, 0, 120000]])
def test_b_and_f_partial_or_incomplete_imports_never_lower_the_declared_income(partial):
    result = baseline(DECLARED, partial, imported=partial)
    assert (result["baseline"], result["source"]) == (1000000, "declared")


def test_c_imports_above_the_declared_income_neither_raise_it_nor_add_to_it():
    result = baseline(DECLARED, [1500000, 1500000], imported=[1500000, 1500000])
    assert result["baseline"] == 1000000 and result["monthly_income"] == 1000000


def test_d_without_declared_income_imports_are_the_evidence():
    result = baseline({}, [700000, 700000], imported=[700000, 700000])
    assert (result["baseline"], result["source"]) == (700000, "recorded")


def test_e_manual_income_keeps_the_conservative_cap_and_is_never_added_to_the_declared():
    assert baseline(DECLARED, [600000, 600000, 600000])["baseline"] == 600000
    lower_import = baseline(DECLARED, [700000], imported=[100000])  # 600k manual + 100k imported
    assert lower_import["baseline"] == 600000
    above = baseline(DECLARED, [1200000, 1200000])
    assert above["baseline"] == 1000000 and above["monthly_income"] == 1000000


def test_h_internal_transfers_are_never_income(monkeypatch):
    """Internal transfers are stored as transaction_type internal_transfer, never 'income'."""
    db = LedgerDB()
    db.state["profiles"][ACCOUNT].update({"income_type": None, "fixed_monthly_salary": None})
    db.state["transactions"].append({"id": 1, "transaction_date": TODAY.replace(day=1), "description": "Traslado propio",
                                     "amount": 500000, "transaction_type": "internal_transfer", "source": "finva_gmail",
                                     "user_id": 90, "workspace_id": WORKSPACE})
    with db.connect() as conn:
        result = income_policy.load_income_baseline(conn, account_id=ACCOUNT, workspace_id=WORKSPACE, today=TODAY)
    assert (result["baseline"], result["source"]) == (0, "none")


def test_i_variable_income_uses_the_last_three_months_with_income():
    result = baseline({}, [900000, 400000, 800000, 600000])
    assert result["baseline"] == 600000 and result["variability_percent"] > 20


def test_recurring_income_items_are_added_on_top():
    result = baseline(DECLARED, [], recurring=[{"item_type": "income", "amount": 100000, "frequency": "monthly", "is_active": True},
                                               {"item_type": "expense", "amount": 50000, "frequency": "monthly", "is_active": True}])
    assert result["monthly_income"] == 1100000


class ScopedConn:
    """Answers the loader's queries strictly by the workspace/account parameters (scenario J)."""

    def __init__(self, transactions, profiles):
        self.transactions, self.profiles = transactions, profiles

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        q = " ".join(query.split())
        rows = []
        if "FROM financial_profiles" in q:
            rows = [self.profiles[params]] if params in self.profiles else []
        elif q.startswith("SELECT COALESCE((SELECT SUM(amount) FROM salaries"):
            ws, start, end = params[6], params[7], params[8]
            total = sum(t["amount"] for t in self.transactions if t["workspace_id"] == ws and t["type"] == "income" and start <= t["date"] < end)
            rows = [{"income": total, "expenses": 0, "debt_paid": 0}]
        elif "to_char(transaction_date::date,'YYYY-MM')" in q:
            ws, *sources, since = params
            totals = {}
            for t in self.transactions:
                if t["workspace_id"] == ws and t["type"] == "income" and t["source"] in sources and t["date"] >= since:
                    totals[t["date"].strftime("%Y-%m")] = totals.get(t["date"].strftime("%Y-%m"), 0) + t["amount"]
            rows = [{"month": k, "total": v} for k, v in totals.items()]
        elif "FROM finva_recurring_items" in q:
            rows = []
        else:
            raise AssertionError(q[:80])
        return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)


def test_j_another_workspace_never_changes_the_income():
    other = [{"workspace_id": "ws-b", "type": "income", "source": "manual", "amount": 50000, "date": TODAY - timedelta(days=d)} for d in (5, 40, 70)]
    conn = ScopedConn(other, {("acc-a", "ws-a"): DECLARED, ("acc-b", "ws-b"): {}})
    mine = income_policy.load_income_baseline(conn, account_id="acc-a", workspace_id="ws-a", today=TODAY)
    theirs = income_policy.load_income_baseline(conn, account_id="acc-b", workspace_id="ws-b", today=TODAY)
    assert (mine["baseline"], mine["source"]) == (1000000, "declared")
    assert theirs["baseline"] == 50000


# Home vs Strategy -----------------------------------------------------------------

def _strategy(monkeypatch, db, role="user", **overrides):
    stubs = {
        "get_debts": lambda: [dict(d) for d in db.state["debts"] if d["workspace_id"] == WORKSPACE],
        "get_financial_summary": lambda: {}, "calculate_monthly_salary_projection": lambda: {},
        # The Owner engine sees every imported deposit as "income already received".
        "_safe_cycle_report": lambda: {"income": {"expected_total": 0, "received_from_transactions": 18500}},
        "_get_strategy_living_expenses": lambda *_a: {"fixed_living_total": 0}, "get_salvavidas_state": lambda: {},
        "_fetch_post_cut_expenses": lambda *_a: {"total": 0}, "_pending_mandatory_fixed_expenses": lambda *_a: {"total": 0},
        "_fetch_distributable_cash": lambda *_a: 0.0, "_fetch_active_financial_goals": lambda *_a: [],
        "_fetch_investment_portfolio": lambda *_a: {},
    }
    for name, value in {**stubs, **overrides}.items():
        monkeypatch.setattr(strategy_dashboard, name, value)
    monkeypatch.setattr(strategy_dashboard, "get_connection", db.connect)
    token = set_current_user({"id": 41, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": role})
    try:
        return strategy_dashboard.build_local_strategy_blueprint()
    finally:
        reset_current_user(token)


@pytest.fixture
def ledger(monkeypatch):
    db = LedgerDB()
    for module in (vip_service, gmail_service):
        monkeypatch.setattr(module, "get_connection", db.connect)
    return db


def _home():
    token = set_current_user({"id": 41, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    try:
        return vip_service.get_vip_command_center()
    finally:
        reset_current_user(token)


def test_real_regression_profile_and_debt_then_partial_imports(ledger, monkeypatch):
    """Existing profile + debt -> connect mail -> partial import -> Home and Strategy keep their reading."""
    home_before = _home()
    strategy_before = _strategy(monkeypatch, ledger)
    _sync_discovers_accounts(ledger)
    token = set_current_user({"id": 41, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    try:
        gmail_service.review_gmail_candidate(1, "accept")  # one imported deposit of 18,500
        gmail_service.review_gmail_candidate(2, "accept")
    finally:
        reset_current_user(token)
    home_after, strategy_after = _home(), _strategy(monkeypatch, ledger)

    assert home_after["safe_to_spend"] == home_before["safe_to_spend"]
    assert home_after["variable_income"]["conservative"] == 1000000
    for key in ("monthly_income", "recurring_monthly_income", "remaining_income_current_cycle", "total_debt"):
        assert strategy_after[key] == strategy_before[key], key
    # Same interpretation on both screens.
    assert strategy_after["monthly_income"] == home_after["variable_income"]["conservative"] == 1000000
    assert strategy_after["income_received_current_cycle"] == 0  # imported deposits no longer vanish
    assert strategy_after["total_debt"] == 500000
    assert strategy_after["income_policy"]["source"] == "declared"


def test_owner_strategy_keeps_its_own_income_inputs(ledger, monkeypatch):
    result = _strategy(monkeypatch, ledger, role="owner",
                       calculate_monthly_salary_projection=lambda: {"results": {"base_net": 900000}})
    assert result["recurring_monthly_income"] == 900000 and result["income_policy"] is None
