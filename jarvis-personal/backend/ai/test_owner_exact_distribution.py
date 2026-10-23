"""Owner exact-amount distribution (phase 1): the current strategy applied to a confirmed amount.

Two modes over the SAME Director engine (`_build_dynamic_director_allocation`):
- estimate (unchanged): the base comes from the records (account cash + income still to come,
  minus the cycle's pending obligations);
- manual amount: the money the Owner has LEFT after already paying expenses, cards and
  installments. It is the base as typed: no obligation is deducted from it again (that would
  count those payments twice), and the same engine splits all of it.

The mode decides where the base comes from; the strategy decides how it is split. Nothing is
written. Synthetic data only; every loader is stubbed, and any database access fails the test.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from backend.ai import strategy_dashboard as sd
from backend.auth.current_user import reset_current_user, set_current_user

CASH, INCOME_LEFT, STATEMENT, POST_CUT, MANDATORY = 300_000.0, 900_000.0, 120_000.0, 30_000.0, 50_000.0
DEBTS = [
    {"id": 1, "name": "Préstamo sintético", "remaining_amount": 2_000_000, "total_amount": 3_000_000,
     "monthly_payment": 100_000, "interest_rate": 24, "payment_day": 5},
    {"id": 2, "name": "Tarjeta sintética", "remaining_amount": 400_000, "total_amount": 500_000,
     "monthly_payment": 40_000, "interest_rate": 40, "payment_day": 21},
]
DEBT_COMMITMENT = 140_000.0  # both installments still pending in the cycle
OBLIGATIONS = STATEMENT + POST_CUT + DEBT_COMMITMENT + MANDATORY


def _as(role, fn, *args, **kwargs):
    token = set_current_user({"id": 7, "account_id": "acc-test", "workspace_id": "ws-test", "role": role})
    try:
        return fn(*args, **kwargs)
    finally:
        reset_current_user(token)


@pytest.fixture
def owner_inputs(monkeypatch):
    """The Owner engine's loaders, answered in memory; a database access is a failure."""
    state = {"debts": DEBTS, "savings": 50_000.0, "monthly_base": 600_000.0, "goals": [], "cycle": True, "salvavidas": True}

    def no_database(*_a, **_k):
        raise AssertionError("the distribution must not touch the database")

    monkeypatch.setattr(sd, "get_connection", no_database)
    monkeypatch.setattr(sd, "get_debts", lambda: [dict(d) for d in state["debts"]])
    monkeypatch.setattr(sd, "get_financial_summary", lambda: {})
    monkeypatch.setattr(sd, "calculate_monthly_salary_projection",
                        lambda: {"results": {"base_net": 900_000, "projected_net": INCOME_LEFT}})
    monkeypatch.setattr(sd, "_safe_cycle_report", lambda: {} if not state["cycle"] else {
        "income": {"expected_total": INCOME_LEFT, "received_from_transactions": 0},
        "expenses": {"spending_only": STATEMENT}, "debts": {"payments_current_period": 0},
        "cycle": {"start": "2026-10-05", "end_exclusive": "2026-11-05"}})
    monkeypatch.setattr(sd, "_get_strategy_living_expenses", lambda *_a: {"fixed_living_total": 150_000})
    def salvavidas():
        if not state["salvavidas"]:
            raise RuntimeError("synthetic: Salvavidas unavailable")
        return {"current_amount": state["savings"], "monthly_base": state["monthly_base"]}

    monkeypatch.setattr(sd, "get_salvavidas_state", salvavidas)
    monkeypatch.setattr(sd, "_fetch_post_cut_expenses", lambda *_a: {"total": POST_CUT})
    monkeypatch.setattr(sd, "_pending_mandatory_fixed_expenses", lambda *_a: {"total": MANDATORY})
    monkeypatch.setattr(sd, "_fetch_distributable_cash", lambda *_a: CASH)
    monkeypatch.setattr(sd, "_fetch_active_financial_goals", lambda *_a: [dict(g) for g in state["goals"]])
    monkeypatch.setattr(sd, "_fetch_investment_portfolio", lambda *_a, **_k: {})
    return state


def _estimate():
    return _as("owner", sd.build_local_strategy_blueprint)


def _exact(amount, currency="CRC"):
    return _as("owner", sd.get_owner_exact_distribution, amount, currency)["strategy"]


def _engine(base, state):
    """The Director engine called directly, as the reference for both modes."""
    debts = [d for d in state["debts"] if d["remaining_amount"] > 0.01]
    return sd._build_dynamic_director_allocation(
        available_before_allocation=max(base, 0.0), debts=debts,
        goal_reserves=sd._calculate_goal_reserves(state["goals"]),
        savings_total=state["savings"], emergency_monthly_base=state["monthly_base"])


def _split(items):
    """Key, percentage and amount (the blueprint also names the target debt)."""
    return [{k: item[k] for k in ("key", "percentage", "amount")} for item in items]


def _total(items):
    return round(sum(item["amount"] for item in items), 2)


# 1. The estimate keeps its behaviour --------------------------------------------------------

def test_the_estimate_keeps_its_base_formula_and_engine(owner_inputs):
    result = _estimate()
    base = CASH + INCOME_LEFT - OBLIGATIONS
    assert result["distribution_source"] == "estimate"
    assert result["allocation_base_amount"] == round(base, 2)
    formula = result["distribution_formula"]
    assert (formula["cash_available_now"], formula["income"], formula["surplus"], formula["deficit"]) == (CASH, INCOME_LEFT, base, 0)
    assert "manual_available" not in formula
    assert _split(result["allocation_items"]) == _engine(base, owner_inputs)["allocation_items"]


# 2 / 5. The manual amount is the base, with the same strategy --------------------------------

def test_250000_typed_are_the_250000_the_strategy_splits(owner_inputs):
    """The example: what is left (₡250.000) is the base as typed, with ₡340.000 of cycle
    obligations on record that were already paid and are never deducted again."""
    assert OBLIGATIONS > 250_000  # a deduction would leave nothing to split: the test would see it
    result = _exact(250_000)
    assert result["allocation_base_amount"] == 250_000
    assert result["distribution_formula"] == {"manual_available": 250_000, "surplus": 250_000}
    assert _total(result["allocation_items"]) == 250_000  # every colón assigned, none twice
    assert _split(result["allocation_items"]) == _engine(250_000, owner_inputs)["allocation_items"]
    assert result["mode"] == _engine(250_000, owner_inputs)["mode"]


@pytest.mark.parametrize("amount", [1, 250_000, 500_000, 750_000.55, 2_000_000])
def test_the_manual_amount_is_split_by_the_same_engine(owner_inputs, amount):
    result = _exact(amount)
    base = round(amount, 2)  # the amount itself: nothing deducted
    assert result["distribution_source"] == "manual_amount"
    assert result["allocation_base_amount"] == base
    formula = result["distribution_formula"]
    assert formula["manual_available"] == base and formula["surplus"] == base
    for deduction in ("cash_available_now", "income", "statement_spending", "new_spending_after_cut",
                      "debt_commitment", "mandatory_fixed_pending", "deficit"):
        assert deduction not in formula, deduction
    reference = _engine(base, owner_inputs)
    assert _split(result["allocation_items"]) == reference["allocation_items"] and result["mode"] == reference["mode"]
    assert _total(result["allocation_items"]) == base


def test_a_new_amount_recalculates_every_allocation(owner_inputs):
    low, high = _exact(600_000), _exact(1_600_000)
    assert low["allocation_base_amount"] == 600_000 and _total(low["allocation_items"]) == 600_000
    assert high["allocation_base_amount"] == 1_600_000 and _total(high["allocation_items"]) == 1_600_000
    assert _total(high["allocation_items"]) > _total(low["allocation_items"])
    assert {i["key"] for i in high["allocation_items"]} >= {i["key"] for i in low["allocation_items"]}


# 3. Every Director mode the engine has stays coherent ----------------------------------------

@pytest.mark.parametrize("case, mode", [
    ({"savings": 0.0}, "debt_safety"),
    ({"savings": 400_000.0}, "debt_attack"),
    ({"debts": [], "savings": 0.0}, "wealth_building"),
    # A goal is protected first only without costly debt and with the Salvavidas covered.
    ({"debts": [], "savings": 700_000.0, "goals": [{"id": 9, "name": "Meta sintética", "target_amount": 300_000,
                 "current_amount": 0, "target_date": (date.today() + timedelta(days=60)).isoformat(),
                 "priority": "critical", "status": "active"}]}, "goal_protection"),
])
def test_each_director_mode_is_coherent_with_a_manual_amount(owner_inputs, case, mode):
    owner_inputs.update(case)
    result = _exact(1_500_000)
    base = result["allocation_base_amount"]
    assert result["mode"] == mode
    assert all(item["amount"] >= 0 for item in result["allocation_items"])
    assert _total(result["allocation_items"]) == base
    assert _split(result["allocation_items"]) == _engine(base, owner_inputs)["allocation_items"]


# 4 / 13. Switching modes changes nothing ------------------------------------------------------

def test_switching_modes_keeps_the_strategy_and_the_data(owner_inputs):
    before = _estimate()
    _exact(800_000)
    _exact(2_500_000)
    after = _estimate()
    assert after == before  # same strategy, same inputs: the manual mode left nothing behind


# 7. Rounding never assigns more than the base ------------------------------------------------

def test_rounding_never_assigns_more_than_the_base():
    rng = random.Random(376)
    for _ in range(2000):
        # Any number of decimals: an estimated base (income x rates) is not always whole cents.
        base = round(rng.uniform(0, 5_000_000), rng.choice([0, 1, 2, 3, 4, 6]))
        weights = [rng.random() for _ in range(rng.randint(1, 6))]
        keys = ["meta_prioritaria", "ataque_de_deuda", "fondo_de_emergencia", "vida_controlada", "inversion", "metas_o_inversion"]
        amounts = {k: base * w / sum(weights) for k, w in zip(keys, weights)}
        _, items = sd._allocation_from_amounts(amounts, base)
        shown = round(base, 2)  # allocation_base_amount, the base the answer shows
        assert _total(items) <= shown + 1e-9
        assert _total(items) == shown  # the weights cover the base: no cent lost, none added
        assert all(item["amount"] > 0 and round(item["amount"], 2) == item["amount"] for item in items)


def test_rounding_cents_are_exact_on_a_known_case():
    _, items = sd._allocation_from_amounts({"ataque_de_deuda": 0.0166, "fondo_de_emergencia": 0.0166, "vida_controlada": 0.0168}, 0.05)
    assert _total(items) == 0.05 and [i["amount"] for i in items] == [0.02, 0.01, 0.02]


# 8. Obligations on record never shrink the amount; the estimate still deducts them ------------

@pytest.mark.parametrize("pending", [0.0, 340_000.0, 5_000_000.0])
def test_recorded_obligations_never_change_the_exact_base(owner_inputs, monkeypatch, pending):
    """However large the cycle's recorded obligations, the exact base is the amount typed; only
    the estimate (records-based) deducts them."""
    monkeypatch.setattr(sd, "_pending_mandatory_fixed_expenses", lambda *_a: {"total": pending})
    result = _exact(250_000)
    assert result["allocation_base_amount"] == 250_000 and _total(result["allocation_items"]) == 250_000
    estimate = _estimate()
    assert estimate["allocation_base_amount"] == round(max(CASH + INCOME_LEFT - (STATEMENT + POST_CUT + DEBT_COMMITMENT + pending), 0), 2)


def test_missing_inputs_are_warned_not_hidden(owner_inputs):
    # The Salvavidas feeds the engine's emergency rules: unread, it is said, never taken as zero.
    owner_inputs["salvavidas"] = False
    assert "salvavidas_unavailable" in {w["code"] for w in _exact(900_000)["distribution_warnings"]}
    owner_inputs["salvavidas"] = True
    # The cycle's commitments only feed the estimate: the exact amount does not need them.
    owner_inputs["cycle"] = False
    assert _exact(900_000)["distribution_warnings"] == []
    assert "cycle_unavailable" in {w["code"] for w in _estimate()["distribution_warnings"]}
    owner_inputs["cycle"] = True
    assert _exact(900_000)["distribution_warnings"] == [] and _estimate()["distribution_warnings"] == []


# 9. Currencies are never mixed ---------------------------------------------------------------

def test_another_currency_is_refused_never_converted(owner_inputs):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        _as("owner", sd.get_owner_exact_distribution, 500_000, "USD")
    assert refused.value.status_code == 422
    answer = _as("owner", sd.get_owner_exact_distribution, 500_000, "crc")
    assert answer["manual_amount"] == {"amount": 500_000.0, "currency": "CRC"}


# 11. Owner only --------------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["user", "admin", None])
def test_no_one_but_the_owner_gets_an_exact_distribution(owner_inputs, role):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        _as(role, sd.get_owner_exact_distribution, 500_000)
    assert refused.value.status_code == 403


# 6 / 10 / 11 over HTTP -------------------------------------------------------------------------

@pytest.fixture
def client(owner_inputs, monkeypatch):
    from fastapi.testclient import TestClient

    from backend import main

    role = {"value": "owner"}
    monkeypatch.setattr(main, "authenticate_access_token",
                        lambda _token: {"id": 7, "email": "owner@example.test", "role": role["value"], "status": "active",
                                        "account_id": "acc-test", "workspace_id": "ws-test", "plan": "vip"})
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    client = TestClient(main.app)
    client.role = role
    return client


PATH = "/jarvis/premium/strategy-dashboard/exact-distribution"
HEADERS = {"Authorization": "Bearer synthetic"}


@pytest.mark.parametrize("body", [
    {"amount": 0}, {"amount": -5000}, {}, {"amount": ""}, {"amount": "abc"}, {"amount": "1.000,50"},
    {"amount": 10.555}, {"amount": 1_000_000_000.01}, {"amount": 500_000, "currency": "USD"}, {"amount": None},
])
def test_invalid_amounts_are_refused_before_any_calculation(client, monkeypatch, body):
    monkeypatch.setattr(sd, "_owner_strategy_blueprint", lambda **_k: pytest.fail("no calculation for an invalid amount"))
    assert client.post(PATH, json=body, headers=HEADERS).status_code == 422


def test_a_valid_amount_answers_the_dashboard_shape(client):
    response = client.post(PATH, json={"amount": "750000.50", "currency": "CRC"}, headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "manual_amount" and data["manual_amount"] == {"amount": 750000.5, "currency": "CRC"}
    assert data["strategy"]["allocation_base_amount"] == 750_000.50


@pytest.mark.parametrize("role", ["user", "admin"])
def test_a_user_who_is_not_the_owner_is_refused_by_the_route(client, role):
    client.role["value"] = role
    assert client.post(PATH, json={"amount": 500_000}, headers=HEADERS).status_code == 403


def test_the_estimate_route_is_unchanged_and_answers_like_before(client):
    response = client.get("/jarvis/premium/strategy-dashboard", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["source"] == "live_database"
    assert response.json()["strategy"]["distribution_source"] == "estimate"


# 10. The POST writes nothing, through the whole app ----------------------------------------------

def test_the_post_writes_nothing_through_the_whole_app(monkeypatch):
    """The real route and the real Owner engine (no loader stubbed) against the recording database
    of the GET gate (tests/get_route_harness.py): every INSERT/UPDATE/DELETE/UPSERT/TRUNCATE/DDL is
    recorded and never run. The GET gate does not cover POST routes, so this one is run here."""
    from backend.tests.get_route_harness import AUTH, harness

    for role, expected in (("owner", 200), ("user", 403)):
        with harness(monkeypatch, role) as (client, recorder):
            reads = []
            execute = recorder.execute
            recorder.execute = lambda query: (reads.append(query), execute(query))[1]
            response = client.post(PATH, json={"amount": "250000", "currency": "CRC"}, headers=AUTH)
            assert response.status_code == expected, (role, response.text)
            assert recorder.writes == [], (role, recorder.writes)
            if role == "owner":
                assert reads, "the Owner engine really read the database"
                assert response.json()["strategy"]["allocation_base_amount"] == 250000
                assert response.json()["strategy"]["distribution_source"] == "manual_amount"
            else:
                assert not reads, "a refused caller reaches no query"



# CONFIRMAR over HTTP: Owner only, validated before anything runs ---------------------------------

CONFIRM = PATH + "/confirm"
VALID_CONFIRM = {"amount": "254698", "currency": "CRC", "confirmation_key": "confirm-http-0001",
                 "expected_items": [{"key": "vida_controlada", "amount": "254698"}]}


@pytest.mark.parametrize("role", ["user", "admin"])
def test_a_user_who_is_not_the_owner_cannot_confirm(client, monkeypatch, role):
    from backend.ai import owner_distribution

    monkeypatch.setattr(owner_distribution, "get_connection", lambda: pytest.fail("a refused caller reaches no query"))
    client.role["value"] = role
    assert client.post(CONFIRM, json=VALID_CONFIRM, headers=HEADERS).status_code == 403


@pytest.mark.parametrize("change", [
    {"amount": 0}, {"amount": -1}, {"amount": "abc"}, {"amount": 10.555}, {"currency": "USD"},
    {"confirmation_key": ""}, {"confirmation_key": "short"}, {"confirmation_key": "has spaces in it"},
    {"confirmation_key": None}, {"expected_items": []}, {"expected_items": [{"key": "", "amount": 1}]},
    {"expected_items": [{"key": "vida_controlada", "amount": -1}]},
])
def test_an_invalid_confirmation_is_refused_before_anything_runs(client, monkeypatch, change):
    from backend.ai import routes

    monkeypatch.setattr(routes, "confirm_owner_distribution", lambda *_a: pytest.fail("nothing runs"))
    assert client.post(CONFIRM, json={**VALID_CONFIRM, **change}, headers=HEADERS).status_code == 422
