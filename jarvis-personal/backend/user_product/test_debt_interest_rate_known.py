"""A debt's unknown interest rate is not 0% (debts.interest_rate_known, migration 20261006120000).

Persistence: a debt created without a rate is unknown (NULL, FALSE); an explicit 0 or any rate is
known; historical rows (known NULL) keep a rate above 0, and a 0 only for zero-rate financing.
Saving a debt never confirms a rate it was loaded with. VIP: no decision that compares rates is
made from an unknown one (no "Atacar X", no avalanche/hybrid target, no recommended plan, no
"10% or more" conclusion, no payoff estimate), while what doesn't use rates is unchanged.
All data is synthetic.
"""
import copy
from types import SimpleNamespace

import pytest

from backend.ai import strategy_dashboard
from backend.ai.test_strategy_owner_isolation import _as, _users_inputs, users_engine  # noqa: F401 (fixture)
from backend.user_product import basic_service, debt_rates, service, vip_service
from backend.user_product.strategy_engine import build_basic_strategy
from backend.user_product.test_mail_preserves_financial_state import WORKSPACE
from backend.user_product.test_vip_command_center_unknown_not_zero import RecordingDB, _center


# Persistence rules -------------------------------------------------------------------------------

def test_a_new_debt_without_a_rate_is_unknown_never_zero():
    assert debt_rates.rate_for_create(None) == (None, False)


def test_an_explicit_zero_or_any_given_rate_is_known():
    assert debt_rates.rate_for_create(0) == (0.0, True)
    assert debt_rates.rate_for_create(18.5) == (18.5, True)


@pytest.mark.parametrize("row, known", [
    ({"interest_rate": None, "interest_rate_known": None}, None),                       # never given
    ({"interest_rate": None, "interest_rate_known": False}, None),                      # new: unknown
    ({"interest_rate": 0, "interest_rate_known": True}, 0.0),                           # new: real 0%
    ({"interest_rate": 12, "interest_rate_known": True}, 12.0),
    ({"interest_rate": 0, "interest_rate_known": None, "debt_type": "credit_card"}, None),  # historical 0: unverified
    ({"interest_rate": 0, "interest_rate_known": None, "debt_type": "tasa_cero"}, 0.0),     # the type states 0%
    ({"interest_rate": 24, "interest_rate_known": None, "debt_type": "loan"}, 24.0),         # historical > 0: given
])
def test_known_rate_follows_the_canonical_semantics(row, known):
    assert debt_rates.known_interest_rate(row) == known


def test_saving_another_field_never_confirms_a_historical_zero():
    ambiguous = {"interest_rate": 0, "interest_rate_known": None, "debt_type": "credit_card"}
    # A client that sends back the 0 it loaded, or an empty rate: both columns stay as stored.
    assert debt_rates.rate_for_update(ambiguous, 0, None) == (0, None)
    assert debt_rates.rate_for_update(ambiguous, 0, False) == (0, None)
    assert debt_rates.rate_for_update(ambiguous, None, None) == (0, None)


def test_a_zero_sent_for_an_unknown_rate_is_not_a_confirmation():
    # Older clients send an empty rate as 0 (Number(null) is 0): only `confirmed` makes it 0%.
    unknown = {"interest_rate": None, "interest_rate_known": False}
    assert debt_rates.rate_for_update(unknown, 0, None) == (None, False)
    assert debt_rates.rate_for_update(unknown, 0, False) == (None, False)
    assert debt_rates.rate_for_update(unknown, 18, None) == (18.0, True)  # a real rate was typed


def test_the_user_confirming_or_changing_the_rate_makes_it_known():
    ambiguous = {"interest_rate": 0, "interest_rate_known": None, "debt_type": "credit_card"}
    assert debt_rates.rate_for_update(ambiguous, 0, True) == (0.0, True)      # confirmed 0%
    assert debt_rates.rate_for_update(ambiguous, 21, None) == (21.0, True)    # changed
    unknown = {"interest_rate": None, "interest_rate_known": False}
    assert debt_rates.rate_for_update(unknown, 0, True) == (0.0, True)


def test_clearing_a_known_rate_makes_it_unknown_and_resending_it_changes_nothing():
    known = {"interest_rate": 15, "interest_rate_known": True}
    assert debt_rates.rate_for_update(known, None, True) == (None, False)
    assert debt_rates.rate_for_update(known, 15, None) == (15, True)


class _Conn:
    """Records the statements; answers the stored rate for an update."""

    def __init__(self, stored=None):
        self.calls, self.stored = [], stored

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        selects_stored = self.stored is not None and query.lstrip().upper().startswith("SELECT")
        row = self.stored if selects_stored else {"id": 1, "interest_rate": None, "interest_rate_known": None, "debt_type": "other"}
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [row])

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _payload(**kw):
    base = dict(name="Tarjeta sintética", debt_type="credit_card", total_amount=None, remaining_amount=100000,
                monthly_payment=10000, interest_rate=None, payment_day=None, term_months=None, next_payment_date=None,
                interest_rate_confirmed=None)
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.parametrize("given, stored", [(None, (None, False)), (0, (0.0, True)), (9.5, (9.5, True))])
def test_create_user_debt_stores_the_rate_and_whether_it_is_known(monkeypatch, given, stored):
    conn = _Conn()
    monkeypatch.setattr(service, "get_connection", lambda: conn)
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: WORKSPACE)
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: 1)
    monkeypatch.setattr(service, "mark_applied", lambda _c: None)
    service.create_user_debt(_payload(interest_rate=given))
    insert = next(params for sql, params in conn.calls if sql.startswith("INSERT INTO debts"))
    assert (insert[7], insert[8]) == stored  # interest_rate, interest_rate_known (after monthly_payment, monthly_payment_known)


def test_update_user_debt_keeps_an_unconfirmed_historical_zero(monkeypatch):
    conn = _Conn(stored={"interest_rate": 0, "interest_rate_known": None, "debt_type": "credit_card"})
    monkeypatch.setattr(service, "get_connection", lambda: conn)
    monkeypatch.setattr(service, "get_current_workspace_id", lambda: WORKSPACE)
    monkeypatch.setattr(service, "mark_applied", lambda _c: None)
    service.update_user_debt(5, _payload(name="Nuevo nombre", interest_rate=0))
    update = next(params for sql, params in conn.calls if sql.startswith("UPDATE debts"))
    assert (update[6], update[7]) == (0, None)  # interest_rate, interest_rate_known (after the monthly payment pair)
    service.update_user_debt(5, _payload(interest_rate=0, interest_rate_confirmed=True))
    update = [params for sql, params in conn.calls if sql.startswith("UPDATE debts")][-1]
    assert (update[6], update[7]) == (0.0, True)


def test_the_owner_writer_stores_no_rate_as_unknown(monkeypatch):
    from backend.finance import service as finance_service
    conn = _Conn()
    monkeypatch.setattr(finance_service, "get_connection", lambda: conn)
    monkeypatch.setattr(finance_service, "get_current_user_id", lambda: 1)
    monkeypatch.setattr(finance_service, "get_current_workspace_id", lambda: WORKSPACE)
    finance_service.add_debt(name="Sintética", debt_type="loan", total_amount=1000, remaining_amount=900, monthly_payment=100)
    insert = next(params for sql, params in conn.calls if sql.startswith("INSERT INTO debts"))
    assert (insert[5], insert[6]) == (None, False)


def test_the_owner_editor_keeps_an_unconfirmed_historical_zero(monkeypatch):
    from backend.finance import service as finance_service
    conn = _Conn(stored={"id": 5, "installments_paid": 0, "start_date": None, "first_payment_date": None,
                         "interest_rate": 0, "interest_rate_known": None, "debt_type": "credit_card"})
    monkeypatch.setattr(finance_service, "get_connection", lambda: conn)
    monkeypatch.setattr(finance_service, "get_current_user_id", lambda: 1)
    monkeypatch.setattr(finance_service, "get_current_workspace_id", lambda: WORKSPACE)
    edit = dict(debt_id=5, name="Sintética", debt_type="credit_card", total_amount=1000, remaining_amount=900, monthly_payment=100)
    finance_service.update_debt(**edit, interest_rate=0)
    update = next(params for sql, params in conn.calls if sql.startswith("UPDATE debts"))
    assert (update[5], update[6]) == (0, None)  # loaded 0 sent back: still unconfirmed
    finance_service.update_debt(**edit, interest_rate=24)
    update = [params for sql, params in conn.calls if sql.startswith("UPDATE debts")][-1]
    assert (update[5], update[6]) == (24.0, True)


# VIP command center -----------------------------------------------------------------------------

@pytest.fixture
def ledger(monkeypatch):
    database = RecordingDB()
    for module in (vip_service, service, basic_service):
        monkeypatch.setattr(module, "get_connection", database.connect, raising=False)
    own = [debt for debt in database.state["debts"] if debt["workspace_id"] == WORKSPACE]
    # Two debts: the card (rate 30, known) and a loan whose rate was never given.
    loan = {**own[0], "id": 70, "name": "Préstamo sintético", "remaining_amount": 900000, "total_amount": 900000,
            "monthly_payment": 40000, "interest_rate": None, "interest_rate_known": False, "debt_type": "loan"}
    database.state["debts"].append(loan)
    return database


def _with_known_loan_rate(ledger, rate):
    for debt in ledger.state["debts"]:
        if debt.get("id") == 70:
            debt.update(interest_rate=rate, interest_rate_known=True)


def test_vip_never_reads_an_unknown_rate_as_zero_percent(ledger):
    planner = _center()["debt_planner"]
    by_method = {plan["method"]: plan for plan in planner["strategies"]}
    assert by_method["avalanche"]["target"] is None and by_method["finva"]["target"] is None
    assert by_method["avalanche"]["months"] is None and by_method["avalanche"]["interest"] is None
    assert planner["recommended"] is None  # comparing plans needs every rate


def test_vip_names_no_debt_to_attack_while_a_needed_rate_is_missing(ledger):
    center = _center()
    director = center["director"]
    assert director["priority"] == "debt"  # the general priority still holds
    assert "Préstamo" not in director["headline"] and "Tarjeta" not in director["headline"]
    assert director["missing"] == ["debt_interest_rates"]
    assert not any(step["title"].startswith("Abonar a") for step in center["roadmap"])


def test_known_rates_keep_the_previous_behaviour(ledger):
    _with_known_loan_rate(ledger, 12)
    center = _center()
    assert center["director"]["headline"] == "Atacar Tarjeta Sintética"  # 30% > 12%
    assert center["director"]["missing"] == []
    assert {plan["method"]: plan["target"] for plan in center["debt_planner"]["strategies"]}["avalanche"] == "Tarjeta Sintética"
    assert center["debt_planner"]["recommended"] is not None


def test_an_explicit_zero_percent_is_a_real_rate(ledger):
    _with_known_loan_rate(ledger, 0)
    center = _center()
    assert center["director"]["missing"] == [] and center["director"]["headline"] == "Atacar Tarjeta Sintética"


def test_snowball_orders_by_balance_without_rates(ledger):
    snowball = {plan["method"]: plan for plan in _center()["debt_planner"]["strategies"]}["snowball"]
    assert snowball["target"] == "Tarjeta Sintética"  # smallest balance (500.000 < 900.000)


def test_what_doesnt_use_rates_is_unchanged(ledger):
    unknown = _center()["safe_to_spend"]
    _with_known_loan_rate(ledger, 12)
    known = _center()["safe_to_spend"]
    assert unknown == known  # safe to spend, margin, 45-day minimum and missing


def test_reading_the_command_center_still_writes_nothing(ledger):
    before = copy.deepcopy(ledger.state)
    ledger.statements.clear()
    _center()
    assert ledger.state == before
    assert not [s for s in ledger.statements if s.split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]


def test_vip_and_the_owner_read_the_same_contract(ledger):
    assert _center("user")["director"] == _center("owner")["director"]


# VIP Tu plan del mes ----------------------------------------------------------------------------

UNKNOWN_DEBTS = [
    {"id": 1, "name": "Préstamo sintético", "remaining_amount": 2_000_000, "total_amount": 2_500_000,
     "monthly_payment": 80000, "interest_rate": None, "debt_type": "loan"},
    {"id": 2, "name": "Tarjeta Sintética", "remaining_amount": 500_000, "total_amount": 600_000,
     "monthly_payment": 30000, "interest_rate": 20, "debt_type": "credit_card"},
]


def test_the_vip_plan_says_the_rate_is_missing_and_names_no_debt(users_engine):
    users_engine.setattr(strategy_dashboard, "_load_users_strategy_inputs", lambda *_a: _users_inputs(debts=UNKNOWN_DEBTS))
    plan = _as("user", strategy_dashboard.build_local_strategy_blueprint)
    assert plan["warnings"] == ["Falta la tasa de interés de 1 deuda; la prioridad usa los datos disponibles."]
    assert plan["missing"] == ["debt_interest_rates"]
    assert plan["priority"]["kind"] == "debt"
    assert "Préstamo" not in plan["priority"]["title"] and "Tarjeta" not in plan["priority"]["title"]
    assert plan["timeline"] == [] and plan["estimated_debt_free_date"] is None  # no order or payoff from an unknown
    assert plan["primary_debt_name"] is None


def test_the_ten_percent_rule_is_not_concluded_from_a_missing_rate(users_engine):
    users_engine.setattr(strategy_dashboard, "_load_users_strategy_inputs", lambda *_a: _users_inputs(debts=UNKNOWN_DEBTS))
    real, calls = strategy_dashboard._build_dynamic_director_allocation, []
    users_engine.setattr(strategy_dashboard, "_build_dynamic_director_allocation",
                         lambda *a, **kw: calls.append(kw) or real(*a, **kw))
    _as("user", strategy_dashboard.build_local_strategy_blueprint)
    assert calls and all(kw.get("rates_known") is False for kw in calls)  # the plan says the rate is unknown
    director = real(available_before_allocation=500000, debts=UNKNOWN_DEBTS, goal_reserves={}, savings_total=0,
                    emergency_monthly_base=100000, rates_known=False)
    assert "Falta la tasa de interés de una deuda." in director["investment_blockers"]
    assert "Existe deuda con tasa anual de 10% o más." not in director["investment_blockers"]


def test_goals_wait_for_a_missing_rate_instead_of_assuming_cheap_debt():
    from backend.goals.strategy import build_goal_portfolio
    goal = {"id": 1, "name": "Viaje sintético", "status": "active", "target_amount": 100000, "current_amount": 0}
    unknown = build_goal_portfolio([goal], available=50000, one_month_protected=True, highest_debt_apr=None)
    assert unknown["items"][0]["blocked_by"] == "falta la tasa de interés de una deuda" and unknown["active_goal"] is None
    known = build_goal_portfolio([goal], available=50000, one_month_protected=True, highest_debt_apr=5)
    assert known["items"][0]["blocked_by"] is None


def test_the_owners_default_still_reads_its_rates_as_before():
    # Owner callers never pass rates_known: their historical 0 stays 0, as on main.
    director = strategy_dashboard._build_dynamic_director_allocation(
        available_before_allocation=500000, debts=[{"name": "Sintética", "remaining_amount": 1000, "interest_rate": 0}],
        goal_reserves={}, savings_total=0, emergency_monthly_base=100000)
    assert "Falta la tasa de interés de una deuda." not in director["investment_blockers"]


def test_one_debt_with_an_unknown_rate_is_still_named(users_engine):
    single = [UNKNOWN_DEBTS[0]]
    users_engine.setattr(strategy_dashboard, "_load_users_strategy_inputs", lambda *_a: _users_inputs(debts=single))
    plan = _as("user", strategy_dashboard.build_local_strategy_blueprint)
    assert plan["primary_debt_name"] == "Préstamo sintético"  # nothing to compare
    assert plan["missing"] == []  # as the command center: no comparison waits for the rate
    assert plan["warnings"]  # Basic's warning still says it is missing
    assert plan["estimated_debt_free_date"] is None and plan["estimated_total_months"] is None  # payoff needs it


def test_the_vip_plan_with_known_rates_is_unchanged(users_engine):
    plan = _as("user", strategy_dashboard.build_local_strategy_blueprint)  # the harness debts: 30% and 20%
    assert plan["warnings"] == [] and plan["missing"] == []
    assert plan["timeline"] and plan["primary_debt_name"] == plan["timeline"][0]["name"]


def test_the_owners_rules_never_receive_the_unknown_rate_flag():
    # The Owner's blueprint keeps its historical inputs and rules: it never passes rates_known.
    import inspect
    source = inspect.getsource(strategy_dashboard._owner_strategy_blueprint)
    assert "rates_known" not in source


# Basic and Free ---------------------------------------------------------------------------------

def test_basic_keeps_its_missing_rate_warning():
    snapshot = {"monthly_income_estimate": 900000, "essential_monthly_expenses": 300000, "liquid_savings": 0, "emergency_fund_target": 0,
                "debts": debt_rates.with_known_rates([
                    {"id": 1, "name": "Histórica", "remaining_amount": 100000, "monthly_payment": 10000,
                     "interest_rate": 0, "interest_rate_known": None, "debt_type": "credit_card"},
                    {"id": 2, "name": "Tasa cero", "remaining_amount": 100000, "monthly_payment": 10000,
                     "interest_rate": 0, "interest_rate_known": None, "debt_type": "tasa_cero"},
                ]), "goals": []}
    warnings = build_basic_strategy(snapshot).get("warnings") or []
    assert any("Falta la tasa de interés de 1 deuda" in warning for warning in warnings)


def test_strategy_rows_carry_the_same_known_flag_as_the_debts_list():
    rows = debt_rates.with_known_rates([{"interest_rate": 0, "interest_rate_known": None, "debt_type": "loan"},
                                        {"interest_rate": 0, "interest_rate_known": None, "debt_type": "tasa_cero"}])
    assert [(row["interest_rate"], row["interest_rate_known"]) for row in rows] == [(None, False), (0.0, True)]


def test_free_reads_no_rate():
    from backend.user_product import free_service
    import inspect
    assert "interest_rate" not in inspect.getsource(free_service)
