"""A change in the Owner's debt leaves a notice, in the same transaction, on a real PostgreSQL.

Answering what the bank did writes one notice for the Owner, nothing for anyone else, and nothing
when nothing changed or only a reminder moved. Marking one read stays in its workspace. Synthetic data.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.auth.current_user import reset_current_user, set_current_user
from backend.finance import debt_after_extra, owner_change_notices
from backend.tests.test_owner_debt_block_apply_pg import db  # noqa: F401
from backend.tests.test_owner_distribution_confirm_pg import OTHER, WS, admin_uri  # noqa: F401


def _as(ws, fn, *args):
    token = set_current_user({"id": 7, "account_id": "acc-synthetic", "workspace_id": ws, "role": "owner"})
    try:
        return fn(*args)
    finally:
        reset_current_user(token)


def _debt(cur, ws=WS):
    cur.execute("SELECT id FROM debts WHERE workspace_id=%s", (ws,))
    return cur.fetchone()["id"]


def _notices(cur, ws=WS):
    cur.execute("SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key=%s",
                (ws, owner_change_notices.PREFERENCE_KEY))
    row = cur.fetchone()
    return row["preference_value"]["items"] if row else []


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(debt_after_extra, "owner_account_context", lambda *_: True)


def test_a_new_installment_leaves_what_it_was_and_what_it_is(db, owner):  # noqa: F811
    debt_id = _debt(db)
    _as(WS, debt_after_extra.answer, debt_id, {"new_monthly_payment": 50000})
    (notice,) = _notices(db)
    assert (notice["debt_id"], notice["debt_name"], float(notice["old_payment"]), notice["new_payment"]) == (debt_id, "Préstamo sintético", 60000, 50000)
    assert notice["read"] is False
    assert _notices(db, OTHER) == [], "another workspace never gets it"
    db.execute("SELECT monthly_payment FROM debts WHERE id=%s", (debt_id,))
    assert float(db.fetchone()["monthly_payment"]) == 50000


@pytest.mark.parametrize("payload", [{"unchanged": True}, {"remind_on": None}])
def test_nothing_changed_leaves_no_notice(db, owner, payload):  # noqa: F811
    if "remind_on" in payload:
        from backend.core.time import costa_rica_today
        payload = {"remind_on": costa_rica_today().isoformat()}
    _as(WS, debt_after_extra.answer, _debt(db), payload)
    assert _notices(db) == []


def test_other_accounts_leave_no_notice(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(debt_after_extra, "owner_account_context", lambda *_: False)
    _as(WS, debt_after_extra.answer, _debt(db), {"new_monthly_payment": 50000})
    assert _notices(db) == []


def test_reading_one_stays_in_its_workspace(db, owner):  # noqa: F811
    _as(WS, debt_after_extra.answer, _debt(db), {"remaining_installments": 8})
    (notice,) = _notices(db)
    with pytest.raises(HTTPException) as error:
        _as(OTHER, owner_change_notices.mark_read, notice["id"])
    assert error.value.status_code == 404
    assert _notices(db)[0]["read"] is False
    _as(WS, owner_change_notices.mark_read, notice["id"])
    assert _notices(db)[0]["read"] is True
