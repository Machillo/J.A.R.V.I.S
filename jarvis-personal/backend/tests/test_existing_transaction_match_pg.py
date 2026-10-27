"""A mail candidate is compared with the ledger the user already has, on a real PostgreSQL.

Movements entered by hand (or imported before mail was connected) are not mail candidates,
so candidate-to-candidate dedupe never sees them. existing_transaction_matches finds them by
amount in the movement's original currency and date; it never converts, never crosses a
workspace and ignores rows that were saved from a mail candidate. Synthetic data only.

Uses the embedded server of test_financial_ownership_integrity_pg.py
(DINCR_TEST_POSTGRES_URL or pgserver; CI sets DINCR_REQUIRE_PG_TESTS=1).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from backend.tests.test_financial_ownership_integrity_pg import _admin_uri, _with_database

psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.user_product.candidate_resolution import existing_transaction_matches  # noqa: E402

WORKSPACE_A = "00000000-0000-4000-8000-0000000002a0"
WORKSPACE_B = "00000000-0000-4000-8000-0000000002b0"
DAY = date(2026, 10, 20)

SCHEMA = """
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, transaction_date DATE NOT NULL, description TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL, transaction_type TEXT NOT NULL, category TEXT NOT NULL,
    original_amount NUMERIC(12,2), original_currency TEXT, exchange_rate NUMERIC(12,6),
    workspace_id UUID NOT NULL
);
CREATE TABLE finva_email_candidates (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, transaction_id BIGINT REFERENCES transactions(id)
);
"""


@pytest.fixture(scope="module")
def admin_uri(tmp_path_factory):
    return _admin_uri(tmp_path_factory.mktemp("pgserver-ledger-match"))


@pytest.fixture
def pg(admin_uri):
    name = f"ledger_match_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    conn = psycopg2.connect(_with_database(admin_uri, name), cursor_factory=RealDictCursor)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    try:
        yield Conn(conn)
    finally:
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


class Conn:
    """The psycopg-style execute(...).fetchall() the backend uses."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, query, params=()):
        cur = self.raw.cursor()
        cur.execute(query, params)
        return cur


def ledger(pg, *, amount, day=DAY, workspace=WORKSPACE_A, original_amount=None, original_currency=None,
           kind="expense", saved_from_mail=False) -> int:
    row = pg.execute(
        """INSERT INTO transactions(transaction_date,description,amount,transaction_type,category,
               original_amount,original_currency,workspace_id)
           VALUES(%s,'Movimiento sintetico',%s,%s,'Otros',%s,%s,%s) RETURNING id""",
        (day, amount, kind, original_amount, original_currency, workspace),
    ).fetchone()
    if saved_from_mail:
        pg.execute("INSERT INTO finva_email_candidates(workspace_id,transaction_id) VALUES(%s,%s)", (workspace, row["id"]))
    return int(row["id"])


def candidate(*, amount, day=DAY, currency="CRC", original_amount=None, original_currency=None, workspace=WORKSPACE_A):
    return {"workspace_id": workspace, "transaction_date": day, "amount": amount, "currency": currency,
            "original_amount": original_amount, "original_currency": original_currency}


def test_same_colones_amount_within_two_days_is_a_possible_match(pg):
    manual = ledger(pg, amount=40507)
    assert existing_transaction_matches(pg, candidate(amount=40507, day=date(2026, 10, 22))) == [manual]
    assert existing_transaction_matches(pg, candidate(amount=40507, day=date(2026, 10, 23))) == []
    assert existing_transaction_matches(pg, candidate(amount=40508)) == []


def test_a_signed_ledger_amount_still_matches(pg):
    manual = ledger(pg, amount=-130961)
    assert existing_transaction_matches(pg, candidate(amount=130961)) == [manual]


def test_usd_is_compared_in_usd_never_against_colones(pg):
    usd = ledger(pg, amount=22275, original_amount=45, original_currency="USD", kind="income")
    ledger(pg, amount=45)  # 45 colones is a different movement
    multimoney_usd = candidate(amount=45, currency="CRC", original_amount=45, original_currency="USD")
    assert existing_transaction_matches(pg, multimoney_usd) == [usd]
    # The converted colones of a USD row never match a colones candidate.
    assert existing_transaction_matches(pg, candidate(amount=22275)) == []


def test_rows_saved_from_a_mail_candidate_are_left_to_candidate_dedupe(pg):
    ledger(pg, amount=34000, saved_from_mail=True)
    assert existing_transaction_matches(pg, candidate(amount=34000)) == []


def test_another_workspace_is_never_consulted(pg):
    ledger(pg, amount=34000, workspace=WORKSPACE_B)
    assert existing_transaction_matches(pg, candidate(amount=34000)) == []
    assert existing_transaction_matches(pg, candidate(amount=34000, workspace=None)) == []


def test_several_equal_amounts_are_all_reported_not_picked(pg):
    first, second = ledger(pg, amount=8593), ledger(pg, amount=8593, day=date(2026, 10, 21))
    assert existing_transaction_matches(pg, candidate(amount=8593)) == [first, second]
