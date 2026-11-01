"""A matured locked savings block paid into its debt (Owner), on a real PostgreSQL.

POST /jarvis/premium/debt-savings-blocks/{id}/apply records one extraordinary payment to principal
(``record_extra_payment``) with the bank's choice (shorter term, or a lower installment stored) and
closes the block, in one transaction:

- the debt goes down, a ``debt_payments`` 'extra_payment' row and a ``debt_payment`` transaction
  record it, and the block is closed (it leaves the open list);
- a lower installment is stored only when the bank lowered it;
- a retry, double tap or two at once apply it once;
- a block that has not matured, another workspace's block, or a debt that is gone writes nothing;
- more than the debt owes pays it off and says what was left over.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver` (CI requires it). Synthetic data only.
"""
from __future__ import annotations

import threading
import uuid
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import HTTPException

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import Json, RealDictCursor  # noqa: E402

from backend.ai import owner_debt_block_store as store  # noqa: E402
from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402
from backend.tests.test_owner_distribution_confirm_pg import OTHER, SCHEMA, WS, admin_uri  # noqa: E402,F401

TODAY = date(2027, 5, 6)
BLOCK = {"id": "b1", "debt_id": None, "debt_name": "Préstamo sintético", "mode": "block", "weekly_amount": 13500,
         "start_date": "2026-11-05", "maturity_date": "2027-05-05", "term_months": 6}


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database

    name = f"debt_blocks_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    for ws in (WS, OTHER):
        cur.execute("INSERT INTO workspaces (id) VALUES (%s)", (ws,))
        cur.execute("""INSERT INTO debts (workspace_id, name, total_amount, remaining_amount, monthly_payment, interest_rate)
                       VALUES (%s, 'Préstamo sintético', 3000000, 1000000, 60000, 24) RETURNING id""", (ws,))
        debt_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO user_preferences (workspace_id, preference_key, preference_value) VALUES (%s, %s, %s)",
                    (ws, store.PREFERENCE_KEY, Json({"blocks": [{**BLOCK, "debt_id": debt_id}]})))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setattr(store, "costa_rica_today", lambda: TODAY)
    yield cur
    conn.close()
    with admin.cursor() as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    admin.close()


def _apply(payload, ws=WS, block_id="b1"):
    token = set_current_user({"id": 7, "account_id": "acc-synthetic", "workspace_id": ws, "role": "owner"})
    try:
        return store.apply_block(block_id, payload)
    finally:
        reset_current_user(token)


def _debt(cur, ws=WS):
    cur.execute("SELECT id, remaining_amount, monthly_payment FROM debts WHERE workspace_id=%s", (ws,))
    return cur.fetchone()


def _written(cur, ws=WS):
    cur.execute("SELECT COUNT(*) AS n FROM debt_payments WHERE workspace_id=%s", (ws,))
    payments = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM transactions WHERE workspace_id=%s", (ws,))
    return payments, cur.fetchone()["n"]


def _block(cur, ws=WS):
    cur.execute("SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key=%s", (ws, store.PREFERENCE_KEY))
    return store.normalize(cur.fetchone()["preference_value"])[0]


def test_a_matured_block_is_paid_into_its_debt_and_closed(db):
    answer = _apply({"amount": 351000, "outcome": "reduce_term", "remaining_installments": 12})
    assert answer["replayed"] is False
    debt = _debt(db)
    assert (float(debt["remaining_amount"]), float(debt["monthly_payment"])) == (649000, 60000), "a shorter term keeps the installment"
    db.execute("SELECT term_months, installments_paid FROM debts WHERE workspace_id=%s", (WS,))
    term = db.fetchone()
    assert term["term_months"] - term["installments_paid"] == 12, "the installments left the Owner read from the bank"
    db.execute("SELECT payment_type, amount, source FROM debt_payments WHERE workspace_id=%s", (WS,))
    assert [(row["payment_type"], float(row["amount"]), row["source"]) for row in db.fetchall()] == [("extra_payment", 351000, "debt_savings_block")]
    db.execute("SELECT transaction_type, amount, source, notes FROM transactions WHERE workspace_id=%s", (WS,))
    row = db.fetchone()
    assert (row["transaction_type"], float(row["amount"]), row["source"]) == ("debt_payment", 351000, "debt_savings_block")
    assert "debt_savings_block:b1" in row["notes"]
    applied = _block(db)["applied"]
    assert (applied["outcome"], applied["principal_amount"], applied["left_over"]) == ("reduce_term", 351000, 0)
    assert store.open_blocks([_block(db)]) == []
    assert _written(db, OTHER) == (0, 0) and float(_debt(db, OTHER)["remaining_amount"]) == 1000000


def test_a_lower_installment_is_stored_only_when_the_bank_lowered_it(db):
    _apply({"amount": 351000, "outcome": "reduce_installment", "new_monthly_payment": 39000})
    assert float(_debt(db)["monthly_payment"]) == 39000
    with pytest.raises(HTTPException) as error:
        _apply({"amount": 100, "outcome": "reduce_installment"}, ws=OTHER)
    assert error.value.status_code == 422 and _written(db, OTHER) == (0, 0)


def test_a_retry_or_two_at_once_apply_it_once(db):
    results, errors = [], []

    def run():
        try:
            results.append(_apply({"amount": 351000, "outcome": "reduce_term", "remaining_installments": 12}))
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors and sorted(result["replayed"] for result in results) == [False, True, True]
    assert _written(db) == (1, 1) and float(_debt(db)["remaining_amount"]) == 649000


@pytest.mark.parametrize("payload, status", [
    ({"amount": 0, "outcome": "reduce_term"}, 422), ({"amount": "x", "outcome": "reduce_term"}, 422),
    ({"amount": 351000, "outcome": "who_knows"}, 422),
    ({"amount": 351000, "outcome": "reduce_term"}, 422),   # the installments left are the Owner's to say
    ({"amount": 351000, "outcome": "reduce_term", "remaining_installments": 0}, 422),
])
def test_an_invalid_payment_writes_nothing(db, payload, status):
    with pytest.raises(HTTPException) as error:
        _apply(payload)
    assert error.value.status_code == status and _written(db) == (0, 0) and not _block(db).get("applied")


def test_a_block_that_has_not_matured_writes_nothing(db, monkeypatch):
    monkeypatch.setattr(store, "costa_rica_today", lambda: date(2027, 5, 4))
    with pytest.raises(HTTPException) as error:
        _apply({"amount": 351000, "outcome": "reduce_term", "remaining_installments": 12})
    assert error.value.status_code == 409 and _written(db) == (0, 0)


def test_another_workspaces_block_or_a_debt_that_is_gone_writes_nothing(db):
    with pytest.raises(HTTPException) as error:
        _apply({"amount": 351000, "outcome": "reduce_term", "remaining_installments": 12}, block_id="not-mine")
    assert error.value.status_code == 404
    db.execute("DELETE FROM debts WHERE workspace_id=%s", (WS,))
    with pytest.raises(HTTPException) as error:
        _apply({"amount": 351000, "outcome": "reduce_term", "remaining_installments": 12})
    assert error.value.status_code == 404 and _written(db) == (0, 0) and not _block(db).get("applied")


def test_more_than_the_debt_owes_pays_it_off_and_says_what_was_left(db):
    applied = _apply({"amount": 1_050_000, "outcome": "reduce_term", "remaining_installments": 1})["block"]["applied"]
    assert (applied["principal_amount"], applied["new_remaining_amount"], applied["left_over"]) == (1000000, 0, 50000)
    assert float(_debt(db)["remaining_amount"]) == 0
