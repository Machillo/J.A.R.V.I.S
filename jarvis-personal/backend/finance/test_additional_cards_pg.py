"""Additional cards against a real PostgreSQL: a purchase on someone else's card is theirs.

- Marking a card as carried by a person settles its pending purchase notices as that
  person's receivable for the card cycle; none becomes the user's expense.
- Only email purchase notices of that card in this workspace: a statement row, a card
  payment, the holder's own card and another workspace are never touched.
- Repeating it changes nothing. A new notice arriving later is settled the same way.
- "Not additional any more" sends the notices back to review and empties the charge;
  nothing is deleted. Listing the cards writes nothing.

Uses the server and schema of test_receivables_pg.py. All data is synthetic.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.finance.test_receivables_pg import WS_A, WS_B, admin_uri, db, q, snapshot, stored  # noqa: F401  (fixtures)

pytest.importorskip("psycopg2")

ACCOUNT = "account-a"
TODAY = date.today().isoformat()


def notice(conn, *, card, amount, kind="card_purchase", source="email", ws=WS_A, account=ACCOUNT, day=TODAY):
    return q(conn, """INSERT INTO finva_email_candidates (account_id, workspace_id, transaction_date, amount, source_type,
                          movement_kind, movement_direction, source_account_reference)
                      VALUES (%s, %s, %s, %s, %s, %s, 'out', %s) RETURNING id""",
             (account, ws, day, amount, source, kind, f"****{card}"))[0][0]


def states(conn):
    return dict(q(conn, "SELECT id, status FROM finva_email_candidates ORDER BY id"))


def person(conn, name):
    rows = q(conn, "SELECT id FROM receivables WHERE workspace_id = %s AND person_name = %s", (WS_A, name))
    return rows[0][0] if rows else None


def test_marking_a_card_settles_its_purchases_as_the_persons_debt(db):
    from backend.finance import additional_cards

    q(db, "INSERT INTO card_aliases (workspace_id, card_last4, owner_label, relationship, is_primary) VALUES (%s, '9999', 'Titular', 'principal', TRUE)", (WS_A,))
    purchase = notice(db, card="1111", amount=95000)
    small = notice(db, card="1111", amount=4000)
    statement_row = notice(db, card="1111", amount=95000, source="statement")
    payment = notice(db, card="1111", amount=50000, kind="card_payment")
    own_card = notice(db, card="9999", amount=7000)
    elsewhere = notice(db, card="1111", amount=8000, ws=WS_B, account="account-b")

    result = additional_cards.save_additional_card("1111", "Ana Prueba")
    assert result["settled_purchases"] == 2
    after = states(db)
    assert (after[purchase], after[small]) == ("confirmed", "confirmed")
    assert {after[statement_row], after[payment], after[own_card], after[elsewhere]} == {"pending"}
    assert q(db, "SELECT count(*) FROM transactions") == [(0,)]           # never the user's expense
    rid = person(db, "Ana Prueba")
    assert stored(db, rid) == (99000.0, 0.0, 99000.0, "pending")
    assert q(db, "SELECT count(*) FROM receivables WHERE workspace_id = %s", (WS_B,)) == [(0,)]

    additional_cards.save_additional_card("1111", "Ana Prueba")          # repeating it changes nothing
    assert stored(db, rid) == (99000.0, 0.0, 99000.0, "pending")
    assert q(db, "SELECT count(*) FROM receivable_entries WHERE is_archived = FALSE") == [(1,)]


def test_a_later_notice_on_the_card_is_settled_by_the_mail_sync(db):
    from backend.core import database
    from backend.finance import additional_cards

    additional_cards.save_additional_card("1111", "Ana Prueba")
    later = notice(db, card="1111", amount=12000)
    other = notice(db, card="2222", amount=3000)
    with database.get_connection() as conn:                            # what the Owner mail sync does
        assert additional_cards.route_purchase(conn, later, account_id=ACCOUNT, workspace_id=WS_A) is True
        assert additional_cards.route_purchase(conn, other, account_id=ACCOUNT, workspace_id=WS_A) is False
        assert additional_cards.route_purchase(conn, later, account_id="account-b", workspace_id=WS_B) is False
        conn.commit()
    assert states(db)[later] == "confirmed" and states(db)[other] == "pending"
    assert stored(db, person(db, "Ana Prueba")) == (12000.0, 0.0, 12000.0, "pending")


def test_not_additional_any_more_returns_the_purchases_to_review_and_deletes_nothing(db):
    from backend.finance import additional_cards

    purchase = notice(db, card="1111", amount=95000)
    additional_cards.save_additional_card("1111", "Ana Prueba")
    rid = person(db, "Ana Prueba")
    assert additional_cards.stop_additional_card("1111")["released_purchases"] == 1
    assert states(db)[purchase] == "pending"
    assert stored(db, rid) == (0.0, 0.0, 0.0, "completed")
    assert q(db, "SELECT is_archived, amount FROM receivable_entries") == [(True, 95000)]   # history kept
    assert q(db, "SELECT owner_label, relationship FROM card_aliases WHERE card_last4 = '1111'") == [("Ana Prueba", "titular")]
    assert additional_cards.list_additional_cards()["items"] == []


def test_listing_additional_cards_writes_nothing(db):
    from backend.core import database
    from backend.finance import additional_cards

    q(db, "INSERT INTO card_aliases (workspace_id, card_last4, owner_label, relationship, is_primary) VALUES (%s, '1111', 'Ana Prueba', 'adicional', FALSE), (%s, '9999', 'Titular', 'principal', TRUE), (%s, '3333', 'Otra', 'adicional', FALSE)", (WS_A, WS_A, WS_B))
    before = snapshot(db)
    dbname = q(db, "SELECT current_database()")[0][0]
    q(db, f'ALTER DATABASE "{dbname}" SET default_transaction_read_only = on')
    database.close_idle_connections()
    try:
        items = additional_cards.list_additional_cards()["items"]
    finally:
        q(db, f'ALTER DATABASE "{dbname}" RESET default_transaction_read_only')
        database.close_idle_connections()
    assert items == [{"card_last4": "1111", "person_name": "Ana Prueba"}]
    assert snapshot(db) == before


@pytest.mark.parametrize("last4,name", [("12", "Ana"), ("abcd", "Ana"), ("1111", "  "), ("1111", "x" * 81)])
def test_a_card_needs_four_digits_and_a_name(db, last4, name):
    from fastapi import HTTPException
    from backend.finance import additional_cards

    with pytest.raises(HTTPException):
        additional_cards.save_additional_card(last4, name)
    assert q(db, "SELECT count(*) FROM card_aliases") == [(0,)]
