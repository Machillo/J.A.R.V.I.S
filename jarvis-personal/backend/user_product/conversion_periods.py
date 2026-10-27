"""The close a dollar expense waiting for its conversion belongs to (pure, no database).

Kenneth's rule: a dollar expense paid with a credit card is converted at that card's statement cut;
one without a card (cash, debit, a dollar account) at the end of its calendar month. One rate then
converts every expense of that close.

- Card period: the card's declared cut day `c` (1–31). In a month shorter than `c` the cut is that
  month's last day. An expense on day `d` belongs to the first cut on or after `d`; the period runs
  from the day after the previous cut to that cut, both included.
- Month period: the expense's calendar month.
- A card without a declared cut day is never given one: its expenses fall in their calendar month
  and the period says the cut day is missing, so the app can ask for it.

A period can be closed once it has ended (its last day is today or earlier, Costa Rica time).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Period:
    kind: str  # "card" or "month"
    start: date
    end: date
    account_id: int | None = None  # the card (account_balances.id) of a card period
    cut_day_missing: bool = False  # paid with a card whose cut day is not declared

    @property
    def key(self) -> str:
        """Stable id of the close: the same expenses always fall in the same key."""
        if self.kind == "card":
            return f"card:{self.account_id}:{self.end.isoformat()}"
        return f"month:{self.start.strftime('%Y-%m')}"

    def closable(self, today: date) -> bool:
        return self.end <= today


def cut_date(year: int, month: int, cut_day: int) -> date:
    """The cut of `month`: the declared day, or the month's last day when the month is shorter."""
    return date(year, month, min(cut_day, calendar.monthrange(year, month)[1]))


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def card_period(day: date, cut_day: int, account_id: int) -> Period:
    if not 1 <= cut_day <= 31:
        raise ValueError("cut day is 1 to 31")
    this_cut = cut_date(day.year, day.month, cut_day)
    if day <= this_cut:
        end = this_cut
        previous = cut_date(*_previous_month(day.year, day.month), cut_day)
    else:
        end = cut_date(*_next_month(day.year, day.month), cut_day)
        previous = this_cut
    return Period("card", previous + timedelta(days=1), end, account_id=account_id)


def month_period(day: date, *, cut_day_missing: bool = False) -> Period:
    last = calendar.monthrange(day.year, day.month)[1]
    return Period("month", day.replace(day=1), day.replace(day=last), cut_day_missing=cut_day_missing)


def period_for(day: date, *, account_id: int | None, account_type: str | None, cut_day: int | None) -> Period:
    """The close of an expense on `day`, paid with `account_id` (None = not told)."""
    if account_id is not None and account_type == "credit_card":
        if cut_day is not None:
            return card_period(day, int(cut_day), account_id)
        return month_period(day, cut_day_missing=True)
    return month_period(day)
