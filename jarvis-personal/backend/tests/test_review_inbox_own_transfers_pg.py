"""Movements between the user's own accounts never wait in "Por revisar", on a real PostgreSQL.

A pending candidate already proven to be an own transfer (both ends are accounts the user
confirmed as own) is not something to review: the pending list and the pending badge leave it
out. It stays pending, so re-evaluation can still undo the pairing when an account turns out not
to be the user's, and every other filter still lists it. Confirming an account as own also
re-resolves pending card payments, which name both ends (the paying account and the card).
Synthetic data only.

Uses the embedded server of test_financial_ownership_integrity_pg.py
(DINCR_TEST_POSTGRES_URL or pgserver; CI sets DINCR_REQUIRE_PG_TESTS=1).
"""
from __future__ import annotations

import pytest

from backend.tests.test_accounts_mail_strategy_pg import A, B, _as, _candidate, pg  # noqa: F401  (fixture)
from backend.tests.test_mail_candidate_currency_pg import admin_uri  # noqa: F401  (module fixture)

psycopg2 = pytest.importorskip("psycopg2")

from backend.user_product import candidate_resolution, gmail_service  # noqa: E402


def _own_transfer(pg, ident, *, amount, description):  # noqa: F811
    candidate_id = _candidate(pg, ident, amount=amount, bank="bac", account_id=None, description=description,
                              movement="transfer")
    with pg.cursor() as cur:
        cur.execute(
            """UPDATE finva_email_candidates SET is_internal_transfer=TRUE,transaction_type='internal_transfer',
                   movement_direction='internal',movement_kind='transfer',category='Movimiento interno'
               WHERE id=%s""",
            (candidate_id,),
        )
    return candidate_id


CONNECTION_COLUMNS = """
ALTER TABLE finva_gmail_connections ADD COLUMN IF NOT EXISTS google_email TEXT,
    ADD COLUMN IF NOT EXISTS granted_scopes TEXT[], ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ, ADD COLUMN IF NOT EXISTS watch_expiration TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error TEXT, ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW(), ADD COLUMN IF NOT EXISTS initial_scan_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS initial_scan_completed_at TIMESTAMPTZ, ADD COLUMN IF NOT EXISTS import_scope TEXT,
    ADD COLUMN IF NOT EXISTS import_since DATE;
"""


@pytest.fixture(autouse=True)
def _status_extras(monkeypatch):
    """gmail_status also reports consent and retention; neither is about the pending count."""
    monkeypatch.setattr(gmail_service, "gmail_consent_status", lambda: {})
    monkeypatch.setattr(gmail_service, "retention_policy", lambda: {})


def _badge(pg, ident):  # noqa: F811
    """The pending count the apps show (gmail_status), with the connection columns it reads."""
    with pg.cursor() as cur:
        cur.execute(CONNECTION_COLUMNS)
    return _as(ident, gmail_service.gmail_status)["pending"]


def _listed(ident, status=None):
    return {item["candidate_id"] for item in _as(ident, gmail_service.list_gmail_emails, status)["items"]}


def test_own_transfers_leave_the_pending_list_and_badge_but_stay_reviewable(pg):  # noqa: F811
    purchase = _candidate(pg, A, amount=25000, bank="bac", account_id=None, description="SUPERMERCADO EJEMPLO")
    sent = _own_transfer(pg, A, amount=50000, description="TRASLADO A AHORRO EJEMPLO")
    received = _own_transfer(pg, A, amount=50000, description="ABONO DESDE CUENTA EJEMPLO")

    assert _listed(A, "pending") == {purchase}
    assert _badge(pg, A) == 1
    # Still pending (re-evaluation can undo it) and still visible without the pending filter.
    assert _listed(A) == {purchase, sent, received}
    with pg.cursor() as cur:
        cur.execute("SELECT status FROM finva_email_candidates WHERE id IN (%s,%s)", (sent, received))
        assert {row["status"] for row in cur.fetchall()} == {"pending"}

    # Unpaired again (an account was marked not own): it is something to review again.
    with pg.cursor() as cur:
        cur.execute("UPDATE finva_email_candidates SET is_internal_transfer=FALSE WHERE id=%s", (sent,))
    assert _listed(A, "pending") == {purchase, sent}
    assert _badge(pg, A) == 2

    # Another workspace sees none of it.
    assert _listed(B, "pending") == set() and _badge(pg, B) == 0


def test_an_ownership_change_re_resolves_pending_card_payments(pg, monkeypatch):  # noqa: F811
    payment = _candidate(pg, A, amount=480000, bank="bac", account_id=None, description="PAGO DE TARJETA EJEMPLO",
                         movement="card_payment")
    transfer = _candidate(pg, A, amount=30000, bank="bac", account_id=None, description="TRASLADO EJEMPLO",
                          movement="transfer")
    purchase = _candidate(pg, A, amount=9000, bank="bac", account_id=None, description="FARMACIA EJEMPLO")
    elsewhere = _candidate(pg, B, amount=480000, bank="bac", account_id=None, description="PAGO DE TARJETA EJEMPLO",
                           movement="card_payment")
    with pg.cursor() as cur:
        cur.execute("UPDATE finva_email_candidates SET movement_kind='card_payment' WHERE id IN (%s,%s)", (payment, elsewhere))
        cur.execute("UPDATE finva_email_candidates SET movement_kind='transfer' WHERE id=%s", (transfer,))
        cur.execute("UPDATE finva_email_candidates SET movement_kind='card_purchase' WHERE id=%s", (purchase,))
    resolved = []
    monkeypatch.setattr(candidate_resolution, "resolve_candidate",
                        lambda _conn, candidate_id, **_scope: resolved.append(candidate_id))
    from backend.core.database import get_connection
    with get_connection() as conn:
        count = candidate_resolution.reevaluate_workspace_candidates(conn, account_id=A["account"], workspace_id=A["workspace"])
    assert count == 2 and resolved == sorted([payment, transfer])
