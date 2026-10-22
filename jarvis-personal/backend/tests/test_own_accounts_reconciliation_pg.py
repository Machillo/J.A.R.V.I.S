"""Own accounts and reconciliation from the app, on a real PostgreSQL.

A user can mark as own an account no bank notice ever came from (the other bank of a transfer),
naming its institution, last 4 digits and currency; can say "I don't recognise it" (kept as
pending, never treated as own, with its review date); and a transfer between two own accounts
(also colones -> dollars) is resolved as an internal movement, never income or expense. Two own
accounts that fit the same digits are ambiguous and stay for review. Decisions persist, a second
declaration reuses the account, and nothing crosses workspaces. Synthetic data only.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException

from backend.tests.test_account_ownership_relink_pg import ACCOUNTS
from backend.tests.test_accounts_mail_strategy_pg import A, B, _as, pg  # noqa: F401  (fixture)
from backend.tests.test_mail_candidate_currency_pg import admin_uri  # noqa: F401  (module fixture)

psycopg2 = pytest.importorskip("psycopg2")

from backend.user_product import financial_identity  # noqa: E402
from backend.user_product.candidate_resolution import resolve_candidate  # noqa: E402


# Candidate columns resolution reads that the shared fixture does not create (types as in
# database/migrations; statement_document_id without its foreign key: no statements here).
RESOLUTION_COLUMNS = """
ALTER TABLE finva_email_candidates
    ADD COLUMN IF NOT EXISTS external_reference TEXT,
    ADD COLUMN IF NOT EXISTS semantic_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS movement_kind TEXT NOT NULL DEFAULT 'other',
    ADD COLUMN IF NOT EXISTS transaction_time TIME,
    ADD COLUMN IF NOT EXISTS source_account_reference TEXT,
    ADD COLUMN IF NOT EXISTS destination_account_reference TEXT,
    ADD COLUMN IF NOT EXISTS movement_direction TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS raw_payload JSONB,
    ADD COLUMN IF NOT EXISTS statement_document_id BIGINT,
    ADD COLUMN IF NOT EXISTS movement_index INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS source_account_label TEXT,
    ADD COLUMN IF NOT EXISTS counterparty TEXT,
    ADD COLUMN IF NOT EXISTS source_record_key TEXT,
    ADD COLUMN IF NOT EXISTS institution_country TEXT NOT NULL DEFAULT 'CR',
    ADD COLUMN IF NOT EXISTS dedupe_key TEXT;
-- The ledger match (#370) compares dates: transactions.transaction_date is a DATE, as in production.
ALTER TABLE transactions ALTER COLUMN transaction_date TYPE DATE USING transaction_date::date;
"""


@pytest.fixture
def accounts(pg):  # noqa: F811
    with pg.cursor() as cur:
        cur.execute(ACCOUNTS)
        cur.execute(RESOLUTION_COLUMNS)
    return pg


def _declare(ident, institution, last4, currency="CRC", name=None):
    return _as(ident, financial_identity.declare_own_account, institution, last4, currency, name)["item"]


def _transfer(pg, ident, *, origin, destination, amount=50000, currency="CRC", original=None, bank="bac"):
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id,bank) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (ident["connection"], ident["account"], ident["workspace"], uuid.uuid4().hex, bank),
        )
        message_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,
                   amount,currency,original_amount,original_currency,transaction_type,category,bank,movement_direction,
                   movement_kind,source_account_reference,destination_account_reference,raw_payload)
               VALUES(%s,%s,%s,CURRENT_DATE,'TRANSFERENCIA SINTETICA',%s,%s,%s,%s,'transfer','Transferencias',%s,'out',
                      'transfer',%s,%s,%s) RETURNING id""",
            (message_id, ident["account"], ident["workspace"], amount, currency, amount if original else None, original,
             bank, origin, destination, json.dumps({"movement_direction": "out", "transaction_type": "transfer"})),
        )
        return cur.fetchone()["id"]


def _resolved(pg, candidate_id):
    with financial_identity.get_connection() as conn:
        result = resolve_candidate(conn, candidate_id)
        conn.commit()
    with pg.cursor() as cur:
        cur.execute("SELECT status,is_internal_transfer,transaction_type,transaction_id,resolution_reason FROM finva_email_candidates WHERE id=%s",
                    (candidate_id,))
        return result, dict(cur.fetchone())


def _transactions(pg):
    with pg.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM transactions")
        return cur.fetchone()["n"]


def test_an_account_no_notice_came_from_can_be_declared_own_and_it_persists(accounts):
    item = _declare(A, "multimoney", "6281", "USD")
    assert (item["ownership_status"], item["bank_name"], item["account_last4"], item["currency"], item["source"]) == (
        "own", "MultiMoney", "6281", "USD", "user_declared")
    assert item["ownership_confirmed_at"] is not None
    again = _declare(A, "multimoney", "6281", "USD")
    assert again["id"] == item["id"], "declaring it again reuses the account"
    listed = _as(A, financial_identity.list_financial_identity)
    assert [row["id"] for row in listed["items"]] == [item["id"]] and listed["summary"]["owned"] == 1
    with accounts.cursor() as cur:
        cur.execute("SELECT include_in_net_worth,current_balance FROM account_balances WHERE id=%s", (item["id"],))
        row = cur.fetchone()
    assert row["include_in_net_worth"] is False, "an unknown balance never counts in net worth"


def test_a_later_notice_from_the_declared_account_keeps_it_own(accounts):
    item = _declare(A, "bac", "6121")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****9999")
    with financial_identity.get_connection() as conn:
        row = conn.execute("SELECT * FROM finva_email_candidates WHERE id=%s", (candidate,)).fetchone()
        discovered = financial_identity.discover_candidate_account(
            conn, candidate_id=candidate, candidate=dict(row), account_id=A["account"], workspace_id=A["workspace"])
        conn.commit()
    assert discovered == item["id"]
    assert _as(A, financial_identity.list_financial_identity)["items"][0]["ownership_status"] == "own"


@pytest.mark.parametrize(("institution", "last4", "currency", "name", "message"), [
    ("banco_x", "1234", "CRC", None, "institución"),
    ("bac", "12345", "CRC", None, "4 dígitos"),
    ("bac", "12a4", "CRC", None, "4 dígitos"),
    ("bac", "1234", "EUR", None, "moneda"),
    ("other", "1234", "CRC", None, "nombre de la institución"),
])
def test_an_incomplete_declaration_is_refused(accounts, institution, last4, currency, name, message):
    with pytest.raises(HTTPException) as refused:
        _as(A, financial_identity.declare_own_account, institution, last4, currency, name)
    assert refused.value.status_code == 422 and message in refused.value.detail
    assert _as(A, financial_identity.list_financial_identity)["items"] == []


def test_another_institution_is_named_by_the_user(accounts):
    item = _as(A, financial_identity.declare_own_account, "other", "4321", "CRC", "Coopealianza")["item"]
    assert (item["bank_name"], item["institution_code"], item["ownership_status"]) == ("Coopealianza", "other", "own")


def test_i_dont_recognise_it_is_kept_pending_with_its_review_date(accounts):
    unknown = _declare(A, "multimoney", "4560")
    item = _as(A, financial_identity.confirm_financial_account, unknown["id"], "pending")["item"]
    assert item["ownership_status"] == "pending" and item["ownership_confirmed_at"] is not None
    listed = _as(A, financial_identity.list_financial_identity)
    assert listed["summary"]["owned"] == 0 and listed["summary"]["pending"] == 1


def test_a_transfer_between_two_own_accounts_is_internal_and_creates_no_movement(accounts):
    _declare(A, "bac", "6121")
    _declare(A, "multimoney", "6281")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****6281")
    result, row = _resolved(accounts, candidate)
    assert result == {"status": "internal_transfer"}
    assert row["is_internal_transfer"] is True and row["transaction_type"] == "internal_transfer"
    assert row["resolution_reason"] == "confirmed_owned_endpoints"
    assert row["status"] == "pending" and row["transaction_id"] is None, "nothing is confirmed or saved"
    assert _transactions(accounts) == 0


def test_colones_to_a_dollars_account_is_recognised_on_its_original_currency(accounts):
    """The production case: a BAC transfer whose amount came in USD to the MultiMoney USD account."""
    _declare(A, "bac", "6121", "CRC")
    _declare(A, "multimoney", "6281", "USD")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****6281", amount=140000, original="USD")
    result, row = _resolved(accounts, candidate)
    assert result == {"status": "internal_transfer"} and row["is_internal_transfer"] is True


def test_a_transfer_to_an_unrecognised_account_is_never_internal(accounts):
    _declare(A, "bac", "6121")
    unknown = _declare(A, "multimoney", "4560")
    _as(A, financial_identity.confirm_financial_account, unknown["id"], "pending")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****4560")
    result, row = _resolved(accounts, candidate)
    assert result == {"status": "pending"} and row["is_internal_transfer"] is False
    assert row["transaction_type"] == "transfer", "stays a transfer for review, never income or expense"


def test_two_own_accounts_with_the_same_digits_are_ambiguous_and_stay_for_review(accounts):
    _declare(A, "bac", "6121")
    _declare(A, "bac", "7777")
    _declare(A, "popular", "7777")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****7777")
    result, row = _resolved(accounts, candidate)
    assert result == {"status": "pending"} and row["is_internal_transfer"] is False


def test_marking_an_account_not_mine_or_unknown_undoes_the_internal_transfer(accounts):
    _declare(A, "bac", "6121")
    destination = _declare(A, "multimoney", "6281")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****6281")
    assert _resolved(accounts, candidate)[0] == {"status": "internal_transfer"}
    _as(A, financial_identity.confirm_financial_account, destination["id"], "pending")  # re-evaluates the workspace
    with accounts.cursor() as cur:
        cur.execute("SELECT is_internal_transfer,status,transaction_id FROM finva_email_candidates WHERE id=%s", (candidate,))
        row = cur.fetchone()
    assert row["is_internal_transfer"] is False and row["status"] == "pending" and row["transaction_id"] is None
    assert _transactions(accounts) == 0


def test_resolving_again_never_duplicates_or_saves_anything(accounts):
    _declare(A, "bac", "6121")
    _declare(A, "multimoney", "6281")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****6281")
    for _ in range(3):
        _resolved(accounts, candidate)
    with accounts.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM finva_email_candidates")
        assert cur.fetchone()["n"] == 1
    assert _transactions(accounts) == 0


def test_accounts_and_decisions_never_cross_workspaces(accounts):
    mine = _declare(A, "multimoney", "6281")
    theirs = _declare(B, "multimoney", "6281")
    assert mine["id"] != theirs["id"]
    assert [row["id"] for row in _as(A, financial_identity.list_financial_identity)["items"]] == [mine["id"]]
    with pytest.raises(HTTPException) as refused:
        _as(A, financial_identity.confirm_financial_account, theirs["id"], "pending")
    assert refused.value.status_code == 404
    # B's own account never makes A's transfer internal.
    _declare(A, "bac", "6121")
    _declare(B, "bac", "1111")
    candidate = _transfer(accounts, A, origin="CR00 **** 6121", destination="****1111")
    assert _resolved(accounts, candidate)[0] == {"status": "pending"}
