"""The Owner's automatic savings in Hoy: they fall on Thursdays and leave the statement's result."""
from datetime import date

from backend.ai.owner_commitments import cycle_automatic_savings
from backend.finance import debt_savings_blocks

SALVAVIDAS = {"auto_contribution": {"amount": 1000.0, "enabled": True, "frequency": "weekly", "start_date": "2026-10-29"}}
BLOCK = {"id": "b1", "debt_id": 8, "debt_name": "Deuda", "weekly_amount": 2000.0, "start_date": "2026-11-01",
         "maturity_date": "2027-02-01", "term_months": 3}


def test_a_first_date_that_is_not_a_thursday_moves_to_the_next_thursday():
    dates = debt_savings_blocks.contribution_dates(date(2026, 11, 1), date(2027, 2, 1))
    assert dates[0] == date(2026, 11, 5)
    assert all(day.weekday() == 3 for day in dates)
    assert dates[-1] < date(2027, 2, 1)


def test_a_thursday_start_is_kept():
    assert debt_savings_blocks.contribution_dates(date(2026, 11, 5), date(2026, 11, 20)) == [
        date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 19)]


def test_on_a_thursday_both_savings_are_already_taken():
    savings = cycle_automatic_savings(SALVAVIDAS, [BLOCK], date(2026, 10, 22), date(2026, 11, 21), date(2026, 11, 5))
    # Salvavidas 29 Oct and 5 Nov; the block's first payday 5 Nov.
    assert savings["saved"] == 2 * 1000 + 2000
    # Paydays left: 12 and 19 Nov, both savings.
    assert savings["total"] == 4 * 1000 + 3 * 2000


def test_the_day_before_the_thursday_is_not_taken_yet():
    savings = cycle_automatic_savings(SALVAVIDAS, [BLOCK], date(2026, 10, 22), date(2026, 11, 21), date(2026, 11, 4))
    assert savings["saved"] == 1000


def test_without_automatic_savings_nothing_is_taken():
    assert cycle_automatic_savings({}, [], date(2026, 10, 22), date(2026, 11, 21), date(2026, 11, 5)) == {"saved": 0, "total": 0}


def test_a_statement_before_the_savings_started_takes_nothing():
    savings = cycle_automatic_savings(SALVAVIDAS, [BLOCK], date(2026, 9, 22), date(2026, 10, 21), date(2026, 11, 5))
    assert savings == {"saved": 0, "total": 0}


def test_the_statement_result_gives_up_what_was_saved(monkeypatch):
    from backend.ai import owner_debt_block_store, preferences
    from backend.user_product import vip_service

    monkeypatch.setattr(preferences, "get_preference", lambda key: SALVAVIDAS if key == "salvavidas" else None)
    monkeypatch.setattr(owner_debt_block_store, "stored_blocks", lambda: [BLOCK])
    cycle = {"balance": 100000.0, "period_start": "2026-10-22", "period_end": "2026-11-21"}
    savings = vip_service._owner_cycle_savings(cycle, date(2026, 11, 5))
    assert cycle["automatic_saved"] == 4000
    assert cycle["balance"] == 100000 - 4000
    assert savings["total"] == 10000
