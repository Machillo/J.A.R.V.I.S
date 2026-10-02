"""Receivables against a real PostgreSQL: reading never writes, settling is never income.

- Listing receivables is a pure read; deriving the ledger is the explicit sync.
- An instalment sale is one charge; each cash collection is a ``receivable_payment``
  (money in, receivable down, not income) and never a new sale.
- A non-cash offset is a ``receivable_offset``: receivable down, no cash, no income, no expense.
- An asset sale is cash in but never earned income.
- Another workspace's movements are never touched or linked.

Uses DINCR_TEST_POSTGRES_URL or the embedded `pgserver`; CI sets DINCR_REQUIRE_PG_TESTS=1
so they fail instead of skipping. Tables keep the real names and the columns these flows
touch. All data is synthetic.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import pytest

psycopg2 = pytest.importorskip("psycopg2")

WS_A, WS_B = "00000000-0000-4000-8000-00000000000a", "00000000-0000-4000-8000-00000000000b"
TODAY = date.today().isoformat()

SCHEMA = """
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, transaction_date DATE NOT NULL,
    description TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, category TEXT,
    account TEXT, source TEXT, notes TEXT, original_amount NUMERIC(14,2), original_currency TEXT,
    exchange_rate NUMERIC(14,6), financial_account_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE receivables (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID NOT NULL, person_name TEXT NOT NULL,
    original_amount NUMERIC(14,2) NOT NULL DEFAULT 0, paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    pending_amount NUMERIC(14,2) NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', notes TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual', source_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE receivable_payments (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID NOT NULL,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE, amount NUMERIC(14,2) NOT NULL,
    source_transaction_id BIGINT, notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE receivable_entries (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID NOT NULL,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE, entry_type TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL, description TEXT NOT NULL DEFAULT '', entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source_type TEXT NOT NULL DEFAULT 'manual', source_key TEXT, source_transaction_id BIGINT,
    cycle_start DATE, cycle_end DATE, is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE UNIQUE INDEX uq_receivable_entries_source_key ON receivable_entries(workspace_id, source_key) WHERE source_key IS NOT NULL;
CREATE TABLE card_aliases (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, card_last4 TEXT NOT NULL, owner_label TEXT NOT NULL,
    relationship TEXT, is_primary BOOLEAN NOT NULL DEFAULT FALSE);
CREATE TABLE email_transaction_candidates (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, transaction_id BIGINT, transaction_date DATE NOT NULL,
    amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, card_owner TEXT, card_last4 TEXT, status TEXT);
"""
TABLES = ("transactions", "receivables", "receivable_payments", "receivable_entries", "card_aliases", "email_transaction_candidates")


@pytest.fixture(scope="module")
def admin_uri(tmp_path_factory):
    url = os.getenv("DINCR_TEST_POSTGRES_URL", "").strip()
    if url:
        return url
    try:
        import pgserver
    except ImportError:
        if os.getenv("DINCR_REQUIRE_PG_TESTS") == "1":
            pytest.fail("PostgreSQL tests are required but neither DINCR_TEST_POSTGRES_URL nor pgserver is available.")
        pytest.skip("No PostgreSQL available (set DINCR_TEST_POSTGRES_URL or install pgserver).")
    return pgserver.get_server(tmp_path_factory.mktemp("pgserver"), cleanup_mode="delete").get_uri()


@pytest.fixture
def db(admin_uri, monkeypatch):
    from backend.core import database
    from backend.auth.current_user import reset_current_user, set_current_user

    name = f"receivables_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(admin_uri)
    uri = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    database.close_idle_connections()
    token = set_current_user({"id": 7, "account_id": "account-a", "workspace_id": WS_A, "role": "owner"})
    try:
        yield conn
    finally:
        reset_current_user(token)
        database.close_idle_connections()
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def snapshot(conn):
    return {t: q(conn, f"SELECT * FROM {t} ORDER BY id") for t in TABLES}


def types(conn, ws=WS_A):
    return dict(q(conn, "SELECT transaction_type, count(*) FROM transactions WHERE workspace_id = %s GROUP BY 1", (ws,)))


def test_listing_receivables_writes_nothing_even_when_a_sync_would(db):
    from backend.finance import intelligence
    from backend.core import database

    intelligence.add_receivable_entry(person_name="Ana Prueba", amount=200000, description="Celular", entry_kind="installment_sale")
    # Data the old read used to derive silently: an additional-card purchase and a payer-named income.
    q(db, "INSERT INTO card_aliases (workspace_id, card_last4, owner_label, is_primary) VALUES (%s, '1111', 'Ana Prueba', FALSE), (%s, '9999', 'Titular', TRUE)", (WS_A, WS_A))
    q(db, "INSERT INTO email_transaction_candidates (workspace_id, transaction_id, transaction_date, amount, transaction_type, card_owner, card_last4, status) VALUES (%s, NULL, %s, 5000, 'expense', 'Ana Prueba', '1111', 'confirmed')", (WS_A, TODAY))
    q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source, notes) VALUES (%s, %s, 'SINPE de Ana Prueba', 7000, 'income', 'manual', 'abono')", (WS_A, TODAY))
    before = snapshot(db)
    # The whole database refuses writes while the list is read.
    dbname = q(db, "SELECT current_database()")[0][0]
    q(db, f'ALTER DATABASE "{dbname}" SET default_transaction_read_only = on')
    database.close_idle_connections()
    try:
        listing = intelligence.list_receivables()
    finally:
        q(db, f'ALTER DATABASE "{dbname}" RESET default_transaction_read_only')
        database.close_idle_connections()
    assert snapshot(db) == before
    [item] = listing["items"]
    assert item["person_name"] == "Ana Prueba" and item["current_amount_due"] == 200000.0


def test_sync_is_the_explicit_writer_and_is_idempotent(db):
    from backend.finance import intelligence

    intelligence.add_receivable_entry(person_name="Ana Prueba", amount=100000, description="", entry_kind="loan")
    q(db, "INSERT INTO card_aliases (workspace_id, card_last4, owner_label, is_primary) VALUES (%s, '1111', 'Ana Prueba', FALSE)", (WS_A,))
    q(db, "INSERT INTO email_transaction_candidates (workspace_id, transaction_id, transaction_date, amount, transaction_type, card_owner, card_last4, status) VALUES (%s, NULL, %s, 5000, 'expense', 'Ana Prueba', '1111', 'confirmed')", (WS_A, TODAY))
    q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source, notes) VALUES (%s, %s, 'SINPE de Ana Prueba', 7000, 'income', 'manual', 'abono')", (WS_A, TODAY))
    first = intelligence.sync_receivables()
    after_first = snapshot(db)
    intelligence.sync_receivables()
    assert first["status"] == "OK" and snapshot(db)["receivable_entries"] == after_first["receivable_entries"]
    charges = q(db, "SELECT amount, source_type FROM receivable_entries WHERE entry_type = 'charge' ORDER BY id")
    assert [(float(a), s) for a, s in charges] == [(100000.0, "manual_loan"), (5000.0, "additional_card_auto")]
    # The legacy income is linked once and never rewritten by the sync.
    assert q(db, "SELECT transaction_type FROM transactions") == [("income",)]
    assert float(q(db, "SELECT pending_amount FROM receivables")[0][0]) == 98000.0


def test_instalment_sale_collection_reduces_the_one_sale_and_is_not_income(db):
    from backend.finance import intelligence

    entry = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=200000, description="Celular", entry_kind="installment_sale")
    rid = entry["item"]["id"]
    result = intelligence.apply_receivable_payment(rid, 10000, method="SINPE", payment_date=TODAY)
    assert result["status"] == "OK"
    assert types(db) == {"receivable_payment": 1}
    tx = q(db, "SELECT category, account, notes, original_currency, exchange_rate FROM transactions")[0]
    assert tx[0] == "Cuentas por cobrar" and tx[1] is None and "Método: sinpe" in tx[2] and tx[3] is None and tx[4] is None
    charges = q(db, "SELECT count(*), sum(amount) FROM receivable_entries WHERE entry_type = 'charge'")[0]
    assert charges[0] == 1 and float(charges[1]) == 200000.0      # still one sale
    assert float(q(db, "SELECT pending_amount FROM receivables WHERE id = %s", (rid,))[0][0]) == 190000.0
    assert q(db, "SELECT source_type FROM receivable_entries WHERE entry_type = 'charge'")[0][0] == "manual_installment_sale"


def test_reimbursement_collection_is_cash_in_not_income(db):
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Luis Ejemplo", amount=30000, description="", entry_kind="purchase")["item"]["id"]
    intelligence.apply_receivable_payment(rid, 30000, method="Transferencia", payment_date=TODAY)
    assert types(db) == {"receivable_payment": 1}
    assert q(db, "SELECT status FROM receivables WHERE id = %s", (rid,))[0][0] == "completed"


def test_non_cash_offset_reduces_the_receivable_without_cash_income_or_expense(db):
    from backend.finance import intelligence
    from backend.transactions import analyzer

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=200000, description="", entry_kind="installment_sale")["item"]["id"]
    intelligence.apply_receivable_payment(rid, 18500, method="non_cash_offset", payment_date=TODAY, notes="se netea con lo que el titular le debía")
    assert types(db) == {"receivable_offset": 1}
    row = q(db, "SELECT account, notes FROM transactions")[0]
    assert row[0] == "Compensación sin efectivo" and "Compensación sin efectivo" in row[1]
    entry = q(db, "SELECT entry_type, source_type, source_transaction_id IS NOT NULL FROM receivable_entries WHERE entry_type = 'payment'")[0]
    assert entry == ("payment", "non_cash_offset", True)          # history kept, linked to its record
    assert float(q(db, "SELECT pending_amount FROM receivables WHERE id = %s", (rid,))[0][0]) == 181500.0
    [month] = analyzer.get_monthly_flow()
    assert month["income"] == 0 and month["earned_income"] == 0 and month["expenses"] == 0 and month["receivable_payments"] == 0


def test_linking_an_existing_income_makes_it_a_collection(db):
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    tx_id = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'SINPE recibido', 20000, 'income', 'email_monitor') RETURNING id", (WS_A, TODAY))[0][0]
    intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=tx_id, payment_date=TODAY)
    assert types(db) == {"receivable_payment": 1}
    assert float(q(db, "SELECT pending_amount FROM receivables WHERE id = %s", (rid,))[0][0]) == 30000.0


def test_another_workspace_movement_is_never_linked_or_retyped(db):
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    foreign = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'otro espacio', 20000, 'income', 'manual') RETURNING id", (WS_B, TODAY))[0][0]
    result = intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=foreign, payment_date=TODAY)
    assert result["status"] == "NOT_FOUND"
    assert types(db, WS_B) == {"income": 1}
    assert float(q(db, "SELECT pending_amount FROM receivables WHERE id = %s", (rid,))[0][0]) == 50000.0


def test_asset_sale_is_cash_in_but_never_earned_income(db):
    from backend.transactions import analyzer

    q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, category) VALUES (%s, %s, 'Venta de vehículo (transferencia + efectivo)', 775000, 'asset_sale', 'Venta de activo')", (WS_A, TODAY))
    [month] = analyzer.get_monthly_flow()
    assert month["asset_sale_proceeds"] == 775000.0 and month["income"] == 775000.0
    assert month["earned_income"] == 0
    summary = analyzer.get_transaction_summary()
    assert summary["income"] == 0 and summary["asset_sale_proceeds"] == 775000.0


def test_a_confirmed_mail_naming_a_receivable_person_becomes_that_collection(db, monkeypatch):
    from backend.core import database
    from backend.email_monitor import service
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="installment_sale")["item"]["id"]
    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: WS_A)

    def confirm(description, notes, amount=10000):
        tx_id = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, %s, %s, 'income', 'email_monitor') RETURNING id", (WS_A, TODAY, description, amount))[0][0]
        with database.get_connection() as conn:
            service._auto_apply_receivable_payment_from_candidate(conn, 7, tx_id, {"transaction_type": "income", "description": description, "notes": notes, "amount": amount, "transaction_date": TODAY})
            conn.commit()
        return q(db, "SELECT transaction_type FROM transactions WHERE id = %s", (tx_id,))[0][0]

    assert confirm("SINPE recibido", "payer: Ana Prueba") == "receivable_payment"
    assert confirm("SINPE recibido", "payer: Persona Desconocida") == "income"   # nobody the workspace is owed by
    assert confirm("Ana Prueba", "") == "income"                                 # a name without payment context
    assert float(q(db, "SELECT pending_amount FROM receivables WHERE id = %s", (rid,))[0][0]) == 40000.0
