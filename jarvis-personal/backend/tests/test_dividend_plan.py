"""Plan de dividendos: the calculation, the stock gate and what a save refuses. Invented amounts."""
import pytest
from fastapi import HTTPException

from backend.finance import dividend_plan as dp

OPEN = {"open": True, "blockers": []}
CLOSED = {"open": False, "blockers": [{"code": "expensive_debt"}]}


def config(**overrides):
    base = {"stocks": [{"symbol": "AAA", "share_pct": 100, "yield_pct": 4}], "goal_monthly_usd": 1000, "monthly_amount_usd": 500, "withholding_pct": 30}
    return dp.normalize({**base, **overrides})


def held(value, symbol="AAA", currency="USD"):
    return [{"symbol": symbol, "currency": currency, "market_value": value}]


def test_capital_needed_is_the_goal_over_the_yield_after_withholding():
    result = dp.calculate(config(), held(0), OPEN)
    assert result["net_yield_pct"] == 2.8
    assert result["capital_needed_usd"] == pytest.approx(12_000 / 0.028, abs=0.01)


def test_two_stocks_blend_their_yields_by_share_and_split_the_purchase():
    stocks = [{"symbol": "AAA", "share_pct": 70, "yield_pct": 4}, {"symbol": "BBB", "share_pct": 30, "yield_pct": 2}]
    result = dp.calculate(config(stocks=stocks), held(0), OPEN)
    assert result["blended_yield_pct"] == 3.4
    assert result["buy_this_month"] == [{"symbol": "AAA", "amount_usd": 350}, {"symbol": "BBB", "amount_usd": 150}]


def test_the_projection_reaches_the_target_in_the_months_it_says():
    result = dp.calculate(config(), held(1000), OPEN)
    months, value, rate = result["months_to_goal"], 1000.0, 0.028 / 12
    for _ in range(months):
        value = value * (1 + rate) + 500
    assert value >= result["capital_needed_usd"]
    assert value - 500 - value * rate / (1 + rate) < result["capital_needed_usd"]


@pytest.mark.parametrize("entry", [0, 1000, 50_000])
def test_saving_what_each_horizon_asks_reaches_the_target_on_time(entry):
    result = dp.calculate(config(), held(entry), OPEN)
    rate = 0.028 / 12
    for row in result["monthly_needed"]:
        value = float(entry)
        for _ in range(row["years"] * 12):
            value = value * (1 + rate) + row["amount_usd"]
        assert value == pytest.approx(result["capital_needed_usd"], abs=5)


def test_no_snapshot_is_unknown_not_zero():
    result = dp.calculate(config(), None, OPEN)
    assert result["current_value_usd"] is None and result["missing_usd"] is None
    assert result["net_monthly_dividend_now_usd"] is None and result["months_to_goal"] is None and result["monthly_needed"] == []
    assert result["capital_needed_usd"] is not None


def test_a_snapshot_without_the_stock_is_a_real_zero():
    assert dp.calculate(config(), held(900, symbol="OTHER"), OPEN)["current_value_usd"] == 0


def test_a_position_in_another_currency_is_not_counted_as_dollars():
    assert dp.calculate(config(), held(900, currency="EUR"), OPEN)["current_value_usd"] == 0


def test_without_a_yield_there_is_no_capital_figure():
    result = dp.calculate(config(stocks=[{"symbol": "AAA", "share_pct": 100}]), held(100), OPEN)
    assert result["ready"] is False and result["capital_needed_usd"] is None and result["current_value_usd"] == 100


def test_a_closed_gate_keeps_the_calculation_but_never_says_buy():
    result = dp.calculate(config(), held(100), CLOSED)
    assert result["buy_this_month"] == [] and result["capital_needed_usd"] is not None


def test_no_monthly_amount_means_no_date_and_no_purchase():
    result = dp.calculate(config(monthly_amount_usd=None), held(100), OPEN)
    assert result["months_to_goal"] is None and result["buy_this_month"] == []


def test_nothing_held_and_nothing_added_never_arrives():
    assert dp.calculate(config(monthly_amount_usd=0), held(0), OPEN)["months_to_goal"] is None


SAFE = {"current_amount": 300, "monthly_base": 100}


@pytest.mark.parametrize("debts,salvavidas,codes", [
    ([], SAFE, []),
    ([{"remaining_amount": 100, "interest_rate": 9.99}], SAFE, []),
    ([{"remaining_amount": 0, "interest_rate": 40}], SAFE, []),
    ([{"remaining_amount": 100, "interest_rate": 10}], SAFE, ["expensive_debt"]),
    ([{"remaining_amount": 100, "interest_rate": None}], SAFE, ["debt_rate_unknown"]),
    ([], {"current_amount": 299.99, "monthly_base": 100}, ["salvavidas_short"]),
    ([], {"current_amount": None, "monthly_base": 100}, ["salvavidas_unknown"]),
    ([], {"current_amount": 300, "monthly_base": 0}, ["salvavidas_unknown"]),
])
def test_the_stock_gate(debts, salvavidas, codes):
    gate = dp.stock_gate(debts, salvavidas)
    assert [row["code"] for row in gate["blockers"]] == codes and gate["open"] is (not codes)


@pytest.mark.parametrize("payload", [
    {},
    {"stocks": []},
    {"stocks": [{"symbol": "AAA", "share_pct": 100}] * 3},
    {"stocks": [{"symbol": "bad symbol", "share_pct": 100}]},
    {"stocks": [{"symbol": "AAA", "share_pct": 50}]},
    {"stocks": [{"symbol": "AAA", "share_pct": 50}, {"symbol": "aaa", "share_pct": 50}]},
    {"stocks": [{"symbol": "AAA", "share_pct": 100, "yield_pct": 90}]},
    {"stocks": [{"symbol": "AAA", "share_pct": 100}], "goal_monthly_usd": -5},
    {"stocks": [{"symbol": "AAA", "share_pct": 100}], "monthly_amount_usd": -1},
    {"stocks": [{"symbol": "AAA", "share_pct": 100}], "withholding_pct": 90},
])
def test_a_save_refuses_what_it_cannot_use(payload):
    with pytest.raises(HTTPException) as refused:
        dp.validated(payload)
    assert refused.value.status_code == 422


def test_a_valid_save_keeps_every_value_and_uppercases_the_symbol():
    saved = dp.validated({"stocks": [{"symbol": "aaa", "share_pct": 60, "yield_pct": 3.5}, {"symbol": "BBB.B", "share_pct": 40}],
                          "goal_monthly_usd": 500, "monthly_amount_usd": 0, "withholding_pct": 0})
    assert saved["stocks"][0]["symbol"] == "AAA" and saved["stocks"][1]["yield_pct"] is None
    assert (saved["goal_monthly_usd"], saved["monthly_amount_usd"], saved["withholding_pct"]) == (500, 0, 0)


def chart(symbol="AAA", price=50, dividends=(0.5, 0.5, 0.5, 0.5), currency="USD"):
    return {"chart": {"result": [{"meta": {"symbol": symbol, "currency": currency, "regularMarketPrice": price},
                                  "events": {"dividends": {str(i): {"amount": amount, "date": i} for i, amount in enumerate(dividends)}}}]}}


def test_the_yield_is_a_year_of_dividends_over_the_price():
    found = dp._yield_from_chart("AAA", chart())
    assert found["yield_pct"] == 4 and found["annual_dividend_usd"] == 2 and found["price_usd"] == 50 and found["payments"] == 4


@pytest.mark.parametrize("payload", [
    None, {}, {"chart": {"result": None}}, chart(symbol="OTHER"), chart(currency="EUR"), chart(price=0), chart(price=None),
    chart(dividends=()), chart(dividends=(-1,)), chart(dividends=(40,)),
])
def test_a_yield_that_cannot_be_trusted_is_unknown_not_zero(payload):
    assert dp._yield_from_chart("AAA", payload) is None


def test_only_the_symbol_goes_out_and_a_failure_can_be_typed_instead(monkeypatch):
    seen = {}

    class Answer:
        status_code = 200

        def json(self):
            return chart()

    def get(url, params, headers, timeout):
        seen.update(url=url, params=params)
        return Answer()

    monkeypatch.setattr(dp.requests, "get", get)
    assert dp.lookup_yield(" aaa ")["yield_pct"] == 4
    assert seen["url"].endswith("/AAA") and set(seen["params"]) == {"range", "interval", "events"}

    def down(*_a, **_k):
        raise dp.requests.ConnectionError("down")

    monkeypatch.setattr(dp.requests, "get", down)
    with pytest.raises(HTTPException) as failed:
        dp.lookup_yield("AAA")
    assert failed.value.status_code == 502


def test_a_bad_symbol_never_goes_out(monkeypatch):
    monkeypatch.setattr(dp.requests, "get", lambda *a, **k: pytest.fail("no request"))
    with pytest.raises(HTTPException) as refused:
        dp.lookup_yield("../etc passwd")
    assert refused.value.status_code == 422


def position(symbol, value, currency="USD", kind="STK"):
    return {"symbol": symbol, "currency": currency, "sec_type": kind, "market_value": value}


@pytest.fixture
def yields(monkeypatch):
    table = {"AAA": 4, "BBB": 2}

    def lookup(symbol):
        if symbol not in table:
            raise HTTPException(status_code=502, detail="down")
        return {"yield_pct": table[symbol]}

    monkeypatch.setattr(dp, "lookup_yield", lookup)


def test_one_number_is_enough_his_stock_and_its_yield_come_by_themselves(yields):
    config = dp.goal_from_holdings(1000, [position("AAA", 300)], dp.normalize({}))
    assert config["stocks"] == [{"symbol": "AAA", "share_pct": 100, "yield_pct": 4}] and config["goal_monthly_usd"] == 1000
    result = dp.calculate(dp.normalize(config), [position("AAA", 300)], OPEN)
    assert result["capital_needed_usd"] == pytest.approx(12_000 / 0.028, abs=0.01)
    assert result["missing_usd"] == pytest.approx(12_000 / 0.028 - 300, abs=0.01) and result["monthly_needed"]


def test_two_stocks_share_by_what_each_is_worth_and_add_up_to_100(yields):
    stocks = dp.goal_from_holdings(1000, [position("BBB", 100), position("AAA", 200)], dp.normalize({}))["stocks"]
    assert [s["symbol"] for s in stocks] == ["AAA", "BBB"] and [s["share_pct"] for s in stocks] == [66.67, 33.33]


def test_only_his_two_largest_dollar_stocks_count(yields):
    rows = [position("AAA", 300), position("BBB", 200), position("CCC", 100), position("EUR1", 900, currency="EUR"), position("OPT", 900, kind="OPT")]
    assert [s["symbol"] for s in dp.goal_from_holdings(1000, rows, dp.normalize({}))["stocks"]] == ["AAA", "BBB"]


def test_a_yield_not_found_stays_unknown(yields):
    config = dp.normalize(dp.goal_from_holdings(1000, [position("ZZZ", 100)], dp.normalize({})))
    assert config["stocks"][0]["yield_pct"] is None and dp.calculate(config, [position("ZZZ", 100)], OPEN)["ready"] is False


@pytest.mark.parametrize("goal,rows", [(0, [position("AAA", 1)]), ("abc", [position("AAA", 1)]), (1000, []), (1000, None), (1000, [position("AAA", 0)])])
def test_it_says_what_is_missing_instead_of_guessing(yields, goal, rows):
    with pytest.raises(HTTPException) as refused:
        dp.goal_from_holdings(goal, rows, dp.normalize({}))
    assert refused.value.status_code == 422


def test_it_keeps_what_was_already_set(yields):
    previous = dp.normalize({"withholding_pct": 15, "monthly_amount_usd": 40})
    config = dp.goal_from_holdings(500, [position("AAA", 1)], previous)
    assert config["withholding_pct"] == 15 and config["monthly_amount_usd"] == 40
