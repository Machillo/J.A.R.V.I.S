"""A credit card's statement cut day on a real PostgreSQL, through the real connection wrapper.

Two synthetic workspaces. The cut day is set only on the caller's own, active, owned credit cards;
another workspace's card is "not found"; before the migration (column absent) reads say
"unavailable" and writes answer 503, never 500.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    _create_database,
    _seed_identities,
    admin_uri,
)

psycopg2 = pytest.importorskip("psycopg2")

A, B = IDENTITIES["A"], IDENTITIES["B"]
# The columns the public code reads (production's account_balances), without the new column.
ACCOUNT_BALANCES = """
CREATE TABLE IF NOT EXISTS account_balances (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
    account_id UUID, workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    account_name TEXT NOT NULL, bank_name TEXT NOT NULL DEFAULT '', institution_code TEXT, institution_country TEXT,
    account_type TEXT NOT NULL DEFAULT 'checking', account_last4 TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CRC', ownership_status TEXT NOT NULL DEFAULT 'own',
    ownership_confirmed_at TIMESTAMPTZ, detected_at TIMESTAMPTZ, last_seen_at TIMESTAMPTZ,
    signals_count INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'manual',
    is_active BOOLEAN NOT NULL DEFAULT TRUE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, account_name, account_last4)
)
"""
# The migration's effect (20261026120000), applied by the tests that need it.
ADD_COLUMN = ("ALTER TABLE account_balances ADD COLUMN statement_cut_day SMALLINT "
              "CHECK (statement_cut_day IS NULL OR statement_cut_day BETWEEN 1 AND 31)")
ROWS = [  # name, workspace identity, type, ownership, active
    ("Tarjeta A", A, "credit_card", "own", True),
    ("Cuenta A", A, "checking", "own", True),
    ("Tarjeta pendiente A", A, "credit_card", "pending", True),
    ("Tarjeta inactiva A", A, "credit_card", "own", False),
    ("Tarjeta B", B, "credit_card", "own", True),
]


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(ACCOUNT_BALANCES)
    for n, (name, who, kind, ownership, active) in enumerate(ROWS):
        cur.execute("INSERT INTO account_balances(account_id,workspace_id,account_name,account_type,account_last4,ownership_status,is_active)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s)", (who["account"], who["workspace"], name, kind, f"{1000 + n}", ownership, active))


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.user_product import financial_identity, statement_cut

    uri, conn, drop = _create_database(admin_uri, _seed)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    for module in (financial_identity, statement_cut):  # the caller is workspace A
        monkeypatch.setattr(module, "get_current_account_id", lambda: A["account"])
        monkeypatch.setattr(module, "get_current_workspace_id", lambda: A["workspace"])
    try:
        yield conn
    finally:
        drop()


def _ids(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT account_name, id FROM account_balances")
        return dict(cur.fetchall())


def _day(conn, name: str):
    with conn.cursor() as cur:
        cur.execute("SELECT statement_cut_day FROM account_balances WHERE account_name=%s", (name,))
        return cur.fetchone()[0]


def _status(call) -> tuple[int, str]:
    with pytest.raises(HTTPException) as error:
        call()
    return error.value.status_code, error.value.detail["code"]


def test_before_the_migration_reads_say_unavailable_and_writes_503(db):
    from backend.user_product.financial_identity import list_financial_identity
    from backend.user_product.statement_cut import set_statement_cut_day

    listing = list_financial_identity()
    assert listing["statement_cut_day_available"] is False
    assert all(item["statement_cut_day"] is None for item in listing["items"])
    assert _status(lambda: set_statement_cut_day(_ids(db)["Tarjeta A"], 21)) == (503, "statement_cut_day_unavailable")


def test_the_owner_of_a_card_declares_and_clears_its_cut_day(db):
    from backend.user_product.financial_identity import list_financial_identity
    from backend.user_product.statement_cut import set_statement_cut_day

    with db.cursor() as cur:
        cur.execute(ADD_COLUMN)
    ids = _ids(db)
    result = set_statement_cut_day(ids["Tarjeta A"], 21)
    assert result["item"]["statement_cut_day"] == 21 and _day(db, "Tarjeta A") == 21
    listing = list_financial_identity()
    assert listing["statement_cut_day_available"] is True
    days = {item["account_name"]: item["statement_cut_day"] for item in listing["items"]}
    assert days["Tarjeta A"] == 21 and days["Cuenta A"] is None
    assert "Tarjeta B" not in days  # another workspace's card is not listed
    set_statement_cut_day(ids["Tarjeta A"], None)
    assert _day(db, "Tarjeta A") is None


def test_only_the_callers_own_active_credit_cards_take_a_cut_day(db):
    from backend.user_product.statement_cut import set_statement_cut_day

    with db.cursor() as cur:
        cur.execute(ADD_COLUMN)
    ids = _ids(db)
    assert _status(lambda: set_statement_cut_day(ids["Tarjeta B"], 15)) == (404, "account_not_found")  # never another's
    assert _day(db, "Tarjeta B") is None
    assert _status(lambda: set_statement_cut_day(ids["Tarjeta inactiva A"], 15)) == (404, "account_not_found")
    assert _status(lambda: set_statement_cut_day(ids["Cuenta A"], 15)) == (422, "not_a_credit_card")
    assert _status(lambda: set_statement_cut_day(ids["Tarjeta pendiente A"], 15)) == (409, "not_own_account")
    assert _status(lambda: set_statement_cut_day(ids["Tarjeta A"], 32)) == (422, "invalid_cut_day")
    assert all(_day(db, name) is None for name in ids)  # nothing was written


def test_the_request_requires_the_key_and_a_day_from_1_to_31():
    from pydantic import ValidationError

    from backend.user_product.models import StatementCutDayRequest

    assert StatementCutDayRequest(statement_cut_day=None).statement_cut_day is None  # clears
    for bad in ({}, {"statement_cut_day": 0}, {"statement_cut_day": 32}):
        with pytest.raises(ValidationError):
            StatementCutDayRequest(**bad)
