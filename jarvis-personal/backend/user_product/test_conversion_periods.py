"""The close a waiting dollar expense belongs to: the card's statement cut, or the calendar month."""
from datetime import date

import pytest

from backend.user_product.conversion_periods import card_period, cut_date, month_period, period_for


def test_a_card_expense_belongs_to_the_first_cut_on_or_after_its_day():
    period = card_period(date(2026, 10, 12), 21, account_id=7)
    assert (period.start, period.end, period.key) == (date(2026, 9, 22), date(2026, 10, 21), "card:7:2026-10-21")
    assert card_period(date(2026, 10, 21), 21, 7).end == date(2026, 10, 21)  # the cut day itself closes that cycle
    after = card_period(date(2026, 10, 22), 21, 7)
    assert (after.start, after.end) == (date(2026, 10, 22), date(2026, 11, 21))


def test_a_cut_day_beyond_a_short_month_is_its_last_day():
    assert cut_date(2026, 2, 31) == date(2026, 2, 28)
    assert cut_date(2028, 2, 30) == date(2028, 2, 29)
    february = card_period(date(2026, 2, 15), 31, 3)
    assert (february.start, february.end) == (date(2026, 2, 1), date(2026, 2, 28))
    march = card_period(date(2026, 3, 1), 31, 3)
    assert (march.start, march.end) == (date(2026, 3, 1), date(2026, 3, 31))


def test_cycles_cross_the_year_without_gaps_or_overlaps():
    december = card_period(date(2026, 12, 20), 5, 9)
    january = card_period(date(2027, 1, 3), 5, 9)
    assert december.end == date(2027, 1, 5) and january == december
    assert card_period(date(2027, 1, 6), 5, 9).start == date(2027, 1, 6)


def test_every_day_of_a_year_falls_in_exactly_one_cycle():
    for cut in (1, 15, 28, 30, 31):
        day, seen = date(2026, 1, 1), {}
        while day.year == 2026:
            period = card_period(day, cut, 1)
            assert period.start <= day <= period.end
            seen.setdefault(period.key, []).append(day)
            day = date.fromordinal(day.toordinal() + 1)
        for days in seen.values():  # each cycle is one contiguous run of days
            assert (days[-1] - days[0]).days == len(days) - 1


def test_without_a_card_the_close_is_the_calendar_month():
    period = month_period(date(2026, 10, 12))
    assert (period.start, period.end, period.key) == (date(2026, 10, 1), date(2026, 10, 31), "month:2026-10")
    assert period_for(date(2026, 10, 12), account_id=None, account_type=None, cut_day=None) == period
    debit = period_for(date(2026, 10, 12), account_id=4, account_type="checking", cut_day=None)
    assert debit == period and not debit.cut_day_missing


def test_a_card_without_a_declared_cut_day_is_never_given_one():
    period = period_for(date(2026, 10, 12), account_id=7, account_type="credit_card", cut_day=None)
    assert period.kind == "month" and period.cut_day_missing and period.key == "month:2026-10"
    card = period_for(date(2026, 10, 12), account_id=7, account_type="credit_card", cut_day=21)
    assert card.kind == "card" and card.end == date(2026, 10, 21)


def test_a_period_closes_only_once_it_has_ended():
    period = card_period(date(2026, 10, 12), 21, 7)
    assert not period.closable(date(2026, 10, 20))
    assert period.closable(date(2026, 10, 21)) and period.closable(date(2026, 11, 2))


def test_an_impossible_cut_day_is_refused():
    with pytest.raises(ValueError):
        card_period(date(2026, 10, 12), 0, 7)
