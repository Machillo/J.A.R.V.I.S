"""Patrimonio counts the Owner's locked savings; nobody else's wealth reads them."""
from datetime import date

import pytest

from backend.ai import owner_debt_block_store as store
from backend.user_product import wealth

BLOCK = {"id": "b1", "debt_id": 8, "debt_name": "Deuda", "weekly_amount": 2000.0, "start_date": "2026-10-29",
         "maturity_date": "2027-02-01", "term_months": 3}


class Conn:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        return self

    def fetchall(self):
        return []


@pytest.fixture
def setting(monkeypatch):
    monkeypatch.setattr(wealth, "get_connection", Conn)
    monkeypatch.setattr(wealth, "get_current_workspace_id", lambda: "w")
    monkeypatch.setattr(wealth, "get_current_account_id", lambda: "a")
    monkeypatch.setattr(wealth, "_exists", lambda *_: False)
    monkeypatch.setattr(wealth, "_investments", lambda *_: [])
    monkeypatch.setattr(wealth, "get_salvavidas_state", lambda: {"current_amount": 1000})
    monkeypatch.setattr(store, "stored_blocks", lambda: [BLOCK])
    monkeypatch.setattr(store, "costa_rica_today", lambda: date(2026, 11, 5))


def test_the_owner_counts_what_his_locked_savings_hold_today(setting, monkeypatch):
    monkeypatch.setattr(wealth, "owner_account_context", lambda *_: True)
    result = wealth.get_wealth()
    row = result["assets"]["accounts"][0]
    assert row["amount"] == 2 * 2000  # 29 Oct and 5 Nov
    assert row["id"] < 0
    assert result["assets"]["total"] == 1000 + 4000


def test_a_regular_account_never_reads_them(setting, monkeypatch):
    monkeypatch.setattr(wealth, "owner_account_context", lambda *_: False)
    def refuse():
        raise AssertionError("a regular account read the Owner's blocks")
    monkeypatch.setattr(store, "stored_blocks", refuse)
    result = wealth.get_wealth()
    assert result["assets"]["accounts"] == []
    assert result["assets"]["total"] == 1000
