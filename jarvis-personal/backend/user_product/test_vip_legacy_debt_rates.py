"""The older VIP debt endpoints never read an unknown interest rate as 0% (debts.interest_rate_known).

/user-product/vip/debt-strategies and /user-product/vip/debt-advisory share their engines with the
Owner's /finance routes. The Users routes ask for the canonical rates (`canonical_rates=True`): an
unknown rate stays None, so no avalanche order, recommendation, payoff or interest is computed from
it, while a known 0% stays 0%. The Owner's routes keep the raw stored rate exactly as before.
All data is synthetic.
"""
from types import SimpleNamespace

import pytest

from backend.finance import intelligence, strategic_engine
from backend.user_product import routes, service
from backend.user_product.test_debt_interest_rate_known import _Conn, _payload
from backend.user_product.test_mail_preserves_financial_state import WORKSPACE

# A card with a known 30%, and a loan whose 0 was never confirmed (the old "no rate → 0").
ROWS = [
    {"id": 1, "name": "Préstamo sintético", "debt_type": "loan", "remaining_amount": 900000, "monthly_payment": 40000,
     "interest_rate": 0, "interest_rate_known": None},
    {"id": 2, "name": "Tarjeta sintética", "debt_type": "credit_card", "remaining_amount": 500000, "monthly_payment": 30000,
     "interest_rate": 30, "interest_rate_known": True},
]


def _rows(rows, rate_flag):
    # The flag column is read only when asked for, as the SELECT does.
    return [dict(row) if rate_flag else {k: v for k, v in row.items() if k != "interest_rate_known"} for row in rows]


@pytest.fixture
def debts(monkeypatch):
    current = {"rows": [dict(row) for row in ROWS]}
    monkeypatch.setattr(strategic_engine, "_fetch_debts", lambda rate_flag=False: _rows(current["rows"], rate_flag))

    class Conn:
        def execute(self, query, params=()):
            rows = _rows(current["rows"], "interest_rate_known" in query)
            return SimpleNamespace(fetchall=lambda: rows)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(intelligence, "get_connection", Conn)
    monkeypatch.setattr(intelligence, "get_current_workspace_id", lambda: WORKSPACE)
    monkeypatch.setattr(intelligence, "get_real_availability", lambda: {"money_really_available": 60000})
    return current


def _known_loan(debts, rate):
    debts["rows"][0].update(interest_rate=rate, interest_rate_known=True)


# /vip/debt-strategies ----------------------------------------------------------------------------

def test_debt_strategies_never_rank_or_estimate_from_an_unknown_rate(debts):
    result = strategic_engine.calculate_debt_strategies(canonical_rates=True)
    loan = next(debt for debt in result["debts"] if debt["id"] == 1)
    assert loan["interest_rate"] is None and loan["monthly_interest_rate"] is None  # never 0%
    assert loan["rate_interpretation"] == "tasa_desconocida" and loan["interest_rate_known"] is False
    assert result["avalanche"] is None and result["recommended"] is None  # no false "highest rate first"
    assert result["missing"] == ["debt_interest_rates"]
    items = {item["id"]: item for item in result["minimum_cost"]["items"]}
    assert items[1]["status"] == "RATE_UNKNOWN" and items[1]["total_interest"] is None
    assert items[2]["status"] == "OK" and items[2]["total_interest"] > 0  # the known rate is still estimated
    assert result["minimum_cost"]["total_projected_interest"] is None  # not a total that omits a debt
    assert [item["id"] for item in result["snowball"]["order"]] == [2, 1]  # balance only, as before


def test_debt_strategies_keep_a_known_zero_percent(debts):
    _known_loan(debts, 0)
    result = strategic_engine.calculate_debt_strategies(canonical_rates=True)
    assert result["missing"] == []
    assert result["recommended"]["priority_debt"]["id"] == 2  # 30% before a real 0%
    assert {item["id"]: item["status"] for item in result["minimum_cost"]["items"]} == {1: "OK", 2: "OK"}
    assert result["minimum_cost"]["total_projected_interest"] is not None


def test_one_debt_with_an_unknown_rate_has_nothing_to_compare(debts):
    debts["rows"] = debts["rows"][:1]
    result = strategic_engine.calculate_debt_strategies(canonical_rates=True)
    assert result["missing"] == [] and result["avalanche"]["priority_debt"]["id"] == 1
    assert result["minimum_cost"]["items"][0]["status"] == "RATE_UNKNOWN"  # its cost still needs the rate


def test_the_owner_debt_strategies_keep_the_stored_rate(debts):
    result = strategic_engine.calculate_debt_strategies()
    loan = next(debt for debt in result["debts"] if debt["id"] == 1)
    assert loan["interest_rate"] == 0.0 and loan["rate_interpretation"] == "sin_interes_registrado"
    assert "interest_rate_known" not in loan and "missing" not in result  # the Owner payload is unchanged
    assert result["recommended"]["priority_debt"]["id"] == 2
    assert result["minimum_cost"]["total_projected_interest"] > 0


# /vip/debt-advisory ------------------------------------------------------------------------------

def test_debt_advisory_never_simulates_an_unknown_rate_as_zero(debts):
    result = intelligence.get_debt_advisory(extra_cash=60000, canonical_rates=True)
    by_id = {scenario["debt"]["id"]: scenario for scenario in result["scenarios"]}
    loan = by_id[1]
    assert loan["debt"]["interest_rate"] is None
    assert loan["recommended_scenario"] is None and "falta la tasa de interés" in loan["recommendation"].lower()
    for option in ("baseline_minimum", "A_monthly_amortization", "C_hybrid"):
        assert loan[option]["months"] is None and loan[option]["total_interest"] is None
        assert loan[option]["status"] == "RATE_UNKNOWN"
    assert loan["B_save_and_liquidate"]["estimated_interest_while_saving"] is None
    assert by_id[2]["recommended_scenario"] and by_id[2]["baseline_minimum"]["total_interest"] > 0  # 30% still simulated
    assert result["missing"] == ["debt_interest_rates"]


def test_debt_advisory_keeps_a_known_zero_percent(debts):
    _known_loan(debts, 0)
    result = intelligence.get_debt_advisory(extra_cash=60000, canonical_rates=True)
    loan = next(scenario for scenario in result["scenarios"] if scenario["debt"]["id"] == 1)
    assert loan["debt"]["interest_rate"] == 0.0
    assert loan["recommended_scenario"] is not None and loan["baseline_minimum"]["total_interest"] == 0
    assert result["missing"] == []


def test_the_owner_debt_advisory_keeps_the_stored_rate(debts):
    result = intelligence.get_debt_advisory(extra_cash=60000)
    loan = next(scenario for scenario in result["scenarios"] if scenario["debt"]["id"] == 1)
    assert loan["debt"]["interest_rate"] == 0 and "interest_rate_known" not in loan["debt"]
    assert loan["recommended_scenario"] in {"B", "C"} and loan["baseline_minimum"]["months"] is not None
    assert "missing" not in result


def test_only_the_users_vip_routes_ask_for_the_canonical_rates(monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "require_feature", lambda _feature: None)
    monkeypatch.setattr(routes, "calculate_debt_strategies", lambda **kw: calls.append(("strategies", kw)) or {})
    monkeypatch.setattr(routes, "get_debt_advisory", lambda **kw: calls.append(("advisory", kw)) or {})
    routes.vip_debt_strategies()
    routes.vip_debt_advisory(extra_cash=None)
    assert calls == [("strategies", {"canonical_rates": True}), ("advisory", {"extra_cash": None, "canonical_rates": True})]
    from backend.finance import routes as owner_routes
    import inspect
    for handler in (owner_routes.financial_engine_debt_strategies, owner_routes.debt_advisory):
        assert "canonical_rates" not in inspect.getsource(handler)  # the Owner's /finance routes are unchanged


# Older clients ---------------------------------------------------------------------------------

def test_an_older_client_saving_other_fields_never_confirms_an_unknown_rate(monkeypatch):
    # Older Capacitor builds send an empty rate as 0 (Number(null)) and no confirmation.
    conn = _Conn(stored={"interest_rate": None, "interest_rate_known": False, "debt_type": "loan"})
    monkeypatch.setattr(service, "get_connection", lambda: conn)
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: WORKSPACE)
    monkeypatch.setattr(service, "mark_applied", lambda _c: None)
    service.update_user_debt(5, _payload(name="Otro nombre", interest_rate=0))
    update = next(params for sql, params in conn.calls if sql.startswith("UPDATE debts"))
    assert (update[5], update[6]) == (None, False)


def test_the_owner_editor_never_confirms_an_unknown_rate_from_a_zero(monkeypatch):
    # The Owner's Finance.jsx sends 0 for garbage input: the server keeps the rate unknown.
    from backend.finance import service as finance_service
    conn = _Conn(stored={"id": 5, "installments_paid": 0, "start_date": None, "first_payment_date": None,
                         "interest_rate": None, "interest_rate_known": False, "debt_type": "loan"})
    monkeypatch.setattr(finance_service, "get_connection", lambda: conn)
    monkeypatch.setattr(finance_service, "get_current_user_id", lambda: 1)
    monkeypatch.setattr(finance_service, "get_current_workspace_id", lambda: WORKSPACE)
    finance_service.update_debt(debt_id=5, name="Sintética", debt_type="loan", total_amount=1000, remaining_amount=900,
                                monthly_payment=100, interest_rate=0)
    update = next(params for sql, params in conn.calls if sql.startswith("UPDATE debts"))
    assert (update[5], update[6]) == (None, False)
