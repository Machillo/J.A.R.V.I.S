"""Confirming an account as own links its notices again, on a real PostgreSQL.

"No es mía" unlinks an account's mail candidates; switching it back to "Es mía" must link them
again, or own-transfer pairing (which matches on that link) stays broken. Only the account's own
candidates are linked, by the same signal rule discovery uses (institution + last 4 + currency);
another institution's notice with the same last 4 digits, or another workspace, never is.
Synthetic data only. Re-evaluation itself is covered elsewhere; here it is recorded.
"""
from __future__ import annotations

import uuid

import pytest

from backend.tests.test_accounts_mail_strategy_pg import A, B, _as, pg  # noqa: F401  (fixture)
from backend.tests.test_mail_candidate_currency_pg import admin_uri  # noqa: F401  (module fixture)

psycopg2 = pytest.importorskip("psycopg2")

from backend.user_product import candidate_resolution, financial_identity  # noqa: E402

ACCOUNTS = """
CREATE TABLE account_balances (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, account_id UUID, account_name TEXT, bank_name TEXT,
    institution_code TEXT, institution_country TEXT, account_type TEXT, account_last4 TEXT, currency TEXT,
    current_balance NUMERIC(14,2), source TEXT, include_in_net_worth BOOLEAN, is_active BOOLEAN DEFAULT TRUE,
    ownership_status TEXT, ownership_confirmed_at TIMESTAMPTZ, detected_at TIMESTAMPTZ, last_seen_at TIMESTAMPTZ,
    signals_count INTEGER DEFAULT 0, updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_finva_financial_identity ON account_balances(workspace_id,account_id,institution_code,account_last4,currency)
    WHERE account_id IS NOT NULL AND account_last4 IS NOT NULL AND account_last4<>'';
"""


def _candidate(pg, ident, *, bank, reference, direction="out", currency="CRC"):  # noqa: F811
    with pg.cursor() as cur:
        cur.execute(
            "INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id,bank) VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (ident["connection"], ident["account"], ident["workspace"], uuid.uuid4().hex, bank),
        )
        message_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,
                   amount,currency,transaction_type,category,bank,movement_direction,source_account_reference)
               VALUES(%s,%s,%s,CURRENT_DATE,'TRASLADO EJEMPLO',1000,%s,'transfer','Transferencias',%s,%s,%s) RETURNING id""",
            (message_id, ident["account"], ident["workspace"], currency, bank, direction, reference),
        )
        candidate_id = cur.fetchone()["id"]
    return candidate_id, message_id


def _discover(ident, candidate_id):
    """Discovery exactly as the sync does it: a pending account, the candidate linked."""
    with financial_identity.get_connection() as conn:
        row = conn.execute("SELECT * FROM finva_email_candidates WHERE id=%s", (candidate_id,)).fetchone()
        account = financial_identity.discover_candidate_account(
            conn, candidate_id=candidate_id, candidate=dict(row), account_id=ident["account"], workspace_id=ident["workspace"])
        conn.commit()
    return account


def _link(pg, candidate_id):
    with pg.cursor() as cur:
        cur.execute("SELECT financial_account_id FROM finva_email_candidates WHERE id=%s", (candidate_id,))
        return cur.fetchone()["financial_account_id"]


def test_switching_an_account_back_to_own_links_its_notices_again(pg, monkeypatch):
    with pg.cursor() as cur:
        cur.execute(ACCOUNTS)
    reevaluated = []
    monkeypatch.setattr(candidate_resolution, "reevaluate_workspace_candidates",
                        lambda conn, **kwargs: reevaluated.append(kwargs["workspace_id"]))
    first, _ = _candidate(pg, A, bank="bac", reference="CR00 **** 1234")
    second, _ = _candidate(pg, A, bank="bac", reference="CR00 **** 1234")
    account = _discover(A, first)
    _discover(A, second)
    # Same last 4 at another institution, and the same account digits in another workspace: never linked.
    other_bank, _ = _candidate(pg, A, bank="multimoney", reference="CR00 **** 1234")
    other_workspace, _ = _candidate(pg, B, bank="bac", reference="CR00 **** 1234")
    assert _link(pg, first) == _link(pg, second) == account

    _as(A, financial_identity.confirm_financial_account, account, "not_mine")
    assert _link(pg, first) is None and _link(pg, second) is None

    _as(A, financial_identity.confirm_financial_account, account, "own")
    assert _link(pg, first) == _link(pg, second) == account  # linked again, so pairing can see them
    assert _link(pg, other_bank) != account and _link(pg, other_workspace) is None
    assert reevaluated == [A["workspace"], A["workspace"]]  # resolution re-runs after each change


def test_a_notice_whose_signal_points_elsewhere_is_never_linked(pg, monkeypatch):
    with pg.cursor() as cur:
        cur.execute(ACCOUNTS)
    monkeypatch.setattr(candidate_resolution, "reevaluate_workspace_candidates", lambda conn, **kwargs: None)
    mine, _ = _candidate(pg, A, bank="bac", reference="CR00 **** 1234")
    account = _discover(A, mine)
    usd, _ = _candidate(pg, A, bank="bac", reference="CR00 **** 1234", currency="USD")  # another currency
    other, _ = _candidate(pg, A, bank="bac", reference="CR00 **** 9999")  # other digits
    for candidate in (usd, other):
        with pg.cursor() as cur:
            cur.execute("UPDATE finva_email_candidates SET financial_account_id=NULL WHERE id=%s", (candidate,))
    _as(A, financial_identity.confirm_financial_account, account, "own")
    assert _link(pg, mine) == account
    assert _link(pg, usd) is None and _link(pg, other) is None
