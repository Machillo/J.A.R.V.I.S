"""Locked savings blocks for long debts (Owner): the engine's rules, with synthetic amounts only."""
from datetime import date

from backend.ai.owner_debt_blocks import automatic_savings_monthly, safe_attack
from backend.finance import debt_savings_blocks as blocks

MONDAY = date(2026, 11, 2)   # the next payday is Thursday 2026-11-05


def debt(id, remaining, payoff_month, rate=24.0, minimum=40000.0):
    return {"id": id, "name": f"Deuda {id}", "remaining_amount": remaining, "interest_rate": rate,
            "minimum_payment": minimum, "payoff_month": payoff_month}


def propose(debts, safe=60000.0, probable=None):
    return blocks.propose(today=MONDAY, safe_monthly_attack=safe,
                          probable_monthly_attack=safe if probable is None else probable, debts=debts)


def test_weekly_amounts_are_safe_money_rounded_down_to_500():
    assert blocks.weekly_amount(60000) == 13500       # 60 000 / (52/12) = 13 846
    assert blocks.weekly_amount(-5000) == 0
    assert blocks.next_payday(MONDAY) == date(2026, 11, 5)
    assert blocks.next_payday(date(2026, 11, 5)) == date(2026, 11, 5)


def test_a_long_debt_gets_a_six_month_block_paid_into_it_at_maturity():
    result = propose([debt(1, 1_000_000, 20)])
    assert result["status"] == "proposal" and result["savings_interest_counted"] is False
    block = result["proposal"]
    assert (block["mode"], block["debt"]["id"], block["weekly_amount"], block["term_months"]) == ("block", 1, 13500, 6)
    assert (block["start_date"], block["maturity_date"], block["contributions"]) == ("2026-11-05", "2027-05-05", 26)
    assert block["total_saved"] == block["abono_amount"] == 351000
    assert block["balance_after_abono"] == round(block["balance_at_maturity"] - 351000, 2)
    assert block["recommendation"] == {"choice": "reduce_term", "reason": "saves_interest"}


def test_the_block_matures_before_the_debt_would_be_paid_anyway():
    block = propose([debt(1, 1_000_000, 5)])["proposal"]
    assert block["term_months"] == 4                     # paid in month 5: the block ends a month before


def test_a_block_never_saves_more_than_the_debt_will_owe():
    """Money is never left waiting in a locked account after the debt is gone."""
    block = propose([debt(1, 200_000, 8, rate=0.0, minimum=10000)])["proposal"]
    assert block["term_months"] == 3 and block["weekly_amount"] < 13500     # made smaller to fit
    assert block["weekly_amount"] % 500 == 0 and block["total_saved"] <= block["balance_at_maturity"]
    assert block["lock_cost"] == 0.0 and block["recommendation"]["reason"] == "finishes_sooner"


def test_overtime_and_bonus_shorten_the_block_never_raise_the_weekly_amount():
    """Extras go straight into the debt, so it falls faster: the block must end sooner (or save less)."""
    safe = propose([debt(1, 400_000, 30, rate=0.0, minimum=20000)])["proposal"]
    probable = propose([debt(1, 400_000, 30, rate=0.0, minimum=20000)], probable=120000)["proposal"]
    assert safe["weekly_amount"] == 13500
    assert probable["weekly_amount"] <= safe["weekly_amount"]
    assert probable["total_saved"] < safe["total_saved"] and probable["term_months"] <= safe["term_months"]
    assert probable["total_saved"] <= probable["balance_at_maturity"]


def test_short_debts_are_paid_first_while_a_quarter_is_saved_for_the_next_long_debt():
    result = propose([debt(1, 60_000, 2), debt(2, 900_000, 24)])
    block = result["proposal"]
    assert [item["id"] for item in result["short_debts"]] == [1]
    # A quarter of 13 500 is 3 000, below the bank's ₡3 750 for 3 months: the minimum is proposed.
    assert (block["mode"], block["debt"]["id"], block["weekly_amount"], block["term_months"]) == ("presave", 2, 3750, 3)


def test_only_short_debts_or_no_money_give_no_block():
    assert propose([debt(1, 60_000, 2), debt(2, 30_000, 3)])["status"] == "short_debts_only"
    assert propose([debt(1, 1_000_000, 20)], safe=1000)["status"] == "no_surplus"
    assert propose([])["status"] == "no_debts"
    assert propose([debt(1, 1_000_000, 20)], safe=1000)["proposal"] is None


def test_the_cost_of_locking_is_the_debts_interest_on_the_money_while_it_waits():
    maturity = date(2027, 5, 5)
    dates = blocks.contribution_dates(date(2026, 11, 5), maturity)
    expected = round(sum(13500 * 0.24 / 365 * (maturity - day).days for day in dates), 2)
    assert blocks.lock_cost(13500, dates, maturity, 24.0) == expected
    assert blocks.lock_cost(13500, dates, maturity, None) is None


def test_a_debt_never_paid_within_the_plan_gets_the_default_term():
    assert propose([debt(1, 5_000_000, None)])["proposal"]["term_months"] == blocks.DEFAULT_TERM_MONTHS


def test_the_same_inputs_give_the_same_proposal():
    assert propose([debt(1, 1_000_000, 20)]) == propose([debt(1, 1_000_000, 20)])


def test_the_salvavidas_automatic_savings_come_out_of_the_other_shares_first():
    weekly = {"enabled": True, "amount": 2500, "frequency": "weekly", "start_date": "2026-11-05", "end_date": None}
    assert automatic_savings_monthly({"auto_contribution": weekly}, MONDAY) == round(2500 * 52 / 12, 2)
    assert automatic_savings_monthly({"auto_contribution": {**weekly, "enabled": False}}, MONDAY) == 0.0
    assert automatic_savings_monthly({"auto_contribution": {**weekly, "end_date": "2026-11-20"}}, date(2026, 12, 1)) == 0.0
    assert safe_attack(attack=50000, surplus=80000, automatic=10833.33) == 50000      # the other 30 000 absorb it
    assert safe_attack(attack=50000, surplus=55000, automatic=10833.33) == 44166.67
    assert safe_attack(attack=5000, surplus=5000, automatic=10833.33) == 0.0


def test_the_banks_minimum_per_contribution_is_never_undercut():
    """₡3 750 per contribution for 3 months (the Owner's bank): a smaller block is never proposed."""
    assert blocks.minimum_contribution(3) == 3750 and blocks.minimum_contribution(6) == 0
    # Fitting the block to what a small debt will owe would need less than ₡3 750 a week: pay it directly.
    assert propose([debt(1, 45_000, 6, rate=0.0, minimum=5000)])["status"] == "pay_directly"
    # Pre-saving needs at least the minimum: with ₡3 500 a week of safe money there is no block.
    assert propose([debt(1, 60_000, 2), debt(2, 900_000, 24)], safe=15500)["status"] == "no_surplus"
