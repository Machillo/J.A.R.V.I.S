"""A dollar expense from a mail notice, confirmed without a rate, waits for the close (real PostgreSQL).

The Owner's rule: dollars are accepted as they are, and the one rate is asked at the card's cut. The
confirmation creates a pending expense (never a transaction with an invented amount), dated on the
purchase and linked to the notice's card. Income still needs the rate. Synthetic data only.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.tests.test_mail_candidate_currency_pg import (  # noqa: F401
    A, B, BAC_USD, _all, _as, _candidate, _corrections, _one, admin_uri, pg,
)
from backend.user_product import gmail_service, pending_conversion

PENDING_STATE = """
ALTER TABLE finva_email_candidates ADD COLUMN raw_payload JSONB;
CREATE TABLE account_balances (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, account_name TEXT NOT NULL DEFAULT '',
    account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT '', statement_cut_day SMALLINT
);
CREATE TABLE expenses (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, category TEXT NOT NULL, expense_type TEXT NOT NULL,
    description TEXT, amount NUMERIC(12,2), original_amount NUMERIC(14,2), original_currency TEXT, exchange_rate NUMERIC(14,6),
    financial_account_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT expenses_amount_known_or_pending_check CHECK (
        amount IS NOT NULL OR (original_amount IS NOT NULL AND original_currency IS NOT NULL AND exchange_rate IS NULL))
);
"""


@pytest.fixture
def waits(pg, monkeypatch):
    with pg.cursor() as cur:
        cur.execute(PENDING_STATE)
        cur.execute("INSERT INTO account_balances(workspace_id,account_name,account_type,statement_cut_day)"
                    " VALUES(%s,'Tarjeta','credit_card',21) RETURNING id", (A["workspace"],))
        card = cur.fetchone()["id"]
    monkeypatch.setattr(pending_conversion, "costa_rica_today", lambda: date(2026, 10, 22))
    return card


def _usd(pg, card=None, **extra) -> int:
    candidate_id = _candidate(pg, A, **BAC_USD, **extra)
    with pg.cursor() as cur:
        cur.execute("UPDATE finva_email_candidates SET financial_account_id=%s WHERE id=%s", (card, candidate_id))
    return candidate_id


def _accept(candidate_id, corrections=None):
    return _as(A, gmail_service.review_gmail_candidate, candidate_id, "accept", corrections)


def test_confirming_without_a_rate_leaves_the_dollars_waiting(pg, waits):
    candidate_id = _usd(pg, waits)
    result = _accept(candidate_id)
    assert result["status"] == "confirmed" and result["transaction_id"] is None

    # No colones are invented: no transaction, no event, and the real dollars on a pending expense.
    assert _one(pg, "SELECT COUNT(*) AS n FROM transactions")["n"] == 0
    assert _one(pg, "SELECT COUNT(*) AS n FROM financial_input_events")["n"] == 0
    expense = _one(pg, "SELECT * FROM expenses")
    assert expense["id"] == result["pending_expense_id"]
    assert expense["amount"] is None and expense["exchange_rate"] is None
    assert (str(expense["original_amount"]), expense["original_currency"]) == ("21.00", "USD")
    assert str(expense["workspace_id"]) == A["workspace"] and expense["user_id"] is None
    assert expense["financial_account_id"] == waits and expense["description"] == "HOSTING EJEMPLO"

    row = _one(pg, """SELECT c.status,c.transaction_id,c.amount,c.original_amount,c.raw_payload,m.status AS message_status
                      FROM finva_email_candidates c JOIN finva_email_messages m ON m.id=c.email_message_id WHERE c.id=%s""", (candidate_id,))
    assert (row["status"], row["transaction_id"], row["message_status"]) == ("confirmed", None, "confirmed")
    # The matching-only amount stays, so a statement of the same purchase still finds this row.
    assert (str(row["amount"]), str(row["original_amount"])) == ("10395.00", "21.00")
    assert row["raw_payload"]["pending_expense_id"] == expense["id"]


def test_the_cut_of_the_21st_asks_for_one_rate_and_converts_it(pg, waits):
    _accept(_usd(pg, waits))                    # bought on 2026-09-20: the close of the 21st of September
    listed = _as(A, pending_conversion.list_pending)
    period = listed["periods"][0]
    assert period["key"] == f"card:{waits}:2026-09-21" and period["closable"] is True and not period["cut_day_missing"]
    assert listed["totals"] == [{"currency": "USD", "amount": 21.0, "count": 1}]

    closed = _as(A, pending_conversion.close_period, period["key"], 505.0)
    assert closed["converted"] == 1 and closed["amount"] == 10605.0
    expense = _one(pg, "SELECT amount,original_amount,exchange_rate FROM expenses")
    assert (str(expense["amount"]), str(expense["original_amount"]), float(expense["exchange_rate"])) == ("10605.00", "21.00", 505.0)


def test_the_purchase_day_decides_the_close_not_the_review_day(pg, waits):
    _accept(_usd(pg, waits), _corrections(21) | {"transaction_date": "2026-10-25"})
    assert _as(A, pending_conversion.list_pending)["periods"][0]["key"] == f"card:{waits}:2026-11-21"


def test_a_correction_without_a_rate_also_waits_with_the_corrected_amount(pg, waits):
    candidate_id = _usd(pg, waits)
    _accept(candidate_id, _corrections(20))
    assert str(_one(pg, "SELECT original_amount FROM expenses")["original_amount"]) == "20.00"
    row = _one(pg, "SELECT amount,original_amount,corrected_fields FROM finva_email_candidates WHERE id=%s", (candidate_id,))
    assert (str(row["amount"]), str(row["original_amount"]), row["corrected_fields"]) == ("10395.00", "20.00", ["amount"])


def test_with_a_rate_it_still_converts_now(pg, waits):
    _accept(_usd(pg, waits), _corrections(21, rate=505))
    assert _one(pg, "SELECT COUNT(*) AS n FROM expenses")["n"] == 0
    assert str(_one(pg, "SELECT amount FROM transactions")["amount"]) == "10605.00"


def test_a_second_confirmation_saves_nothing_more(pg, waits):
    candidate_id = _usd(pg, waits)
    _accept(candidate_id)
    assert _accept(candidate_id)["already_reviewed"] is True
    assert _one(pg, "SELECT COUNT(*) AS n FROM expenses")["n"] == 1


def test_dollar_income_still_needs_the_rate_and_leaves_no_trace(pg, waits):
    candidate_id = _usd(pg, waits)
    with pytest.raises(HTTPException) as error:
        _accept(candidate_id, _corrections(21) | {"transaction_type": "income"})
    assert error.value.status_code == 422
    assert _one(pg, "SELECT COUNT(*) AS n FROM expenses")["n"] == 0
    assert _one(pg, "SELECT status FROM finva_email_candidates WHERE id=%s", (candidate_id,))["status"] == "pending"


def test_without_a_card_it_closes_with_the_calendar_month(pg, waits):
    _accept(_usd(pg))
    assert _as(A, pending_conversion.list_pending)["periods"][0]["key"] == "month:2026-09"


def test_another_workspace_can_neither_confirm_nor_see_it(pg, waits):
    candidate_id = _usd(pg, waits)
    with pytest.raises(HTTPException) as error:
        _as(B, gmail_service.review_gmail_candidate, candidate_id, "accept")
    assert error.value.status_code == 404
    _accept(candidate_id)
    assert _as(B, pending_conversion.list_pending)["items"] == []
    assert _all(pg, "SELECT id FROM expenses WHERE workspace_id=%s", (B["workspace"],)) == []
