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
    amount NUMERIC(14,2) NOT NULL, transaction_type TEXT NOT NULL, card_owner TEXT, card_last4 TEXT, status TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
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
    # The legacy payer-named income is linked once and, like any collection, stops being income.
    assert q(db, "SELECT transaction_type FROM transactions") == [("receivable_payment",)]
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


def stored(conn, rid):
    row = q(conn, "SELECT original_amount, paid_amount, pending_amount, status FROM receivables WHERE id = %s", (rid,))[0]
    return float(row[0]), float(row[1]), float(row[2]), row[3]


def test_each_operation_leaves_the_balance_right_and_open_list_refresh_writes_nothing(db):
    """Charges, collections, offsets and reimbursements update the stored balance themselves;
    opening, listing and refreshing the screen afterwards never writes."""
    from backend.core import database
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=200000, description="Celular", entry_kind="installment_sale")["item"]["id"]
    assert stored(db, rid) == (200000.0, 0.0, 200000.0, "pending")                       # charge
    intelligence.apply_receivable_payment(rid, 10000, method="SINPE", payment_date=TODAY)
    assert stored(db, rid) == (200000.0, 10000.0, 190000.0, "partial")                    # cash collection
    intelligence.apply_receivable_payment(rid, 18500, method="non_cash_offset", payment_date=TODAY)
    assert stored(db, rid) == (200000.0, 28500.0, 171500.0, "partial")                    # non-cash offset
    other = intelligence.add_receivable_entry(person_name="Luis Ejemplo", amount=30000, description="", entry_kind="purchase")["item"]["id"]
    refund = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'Reembolso recibido', 30000, 'reimbursement', 'manual') RETURNING id", (WS_A, TODAY))[0][0]
    intelligence.apply_receivable_payment(other, 30000, source_transaction_id=refund, payment_date=TODAY)
    assert stored(db, other) == (30000.0, 30000.0, 0.0, "completed")                       # reimbursement
    assert types(db) == {"receivable_payment": 2, "receivable_offset": 1}

    before = snapshot(db)
    dbname = q(db, "SELECT current_database()")[0][0]
    q(db, f'ALTER DATABASE "{dbname}" SET default_transaction_read_only = on')
    database.close_idle_connections()
    try:
        listings = [intelligence.list_receivables() for _ in range(3)]               # open, list, refresh
    finally:
        q(db, f'ALTER DATABASE "{dbname}" RESET default_transaction_read_only')
        database.close_idle_connections()
    assert snapshot(db) == before
    assert listings[0] == listings[1] == listings[2]
    by_person = {item["person_name"]: item for item in listings[0]["items"]}
    assert by_person["Ana Prueba"]["current_amount_due"] == 171500.0 and by_person["Luis Ejemplo"]["current_amount_due"] == 0.0


def test_mail_card_purchases_update_the_additional_cardholder_without_any_sync(db, monkeypatch):
    from backend.core import database
    from backend.email_monitor import service

    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: WS_A)
    q(db, "INSERT INTO card_aliases (workspace_id, card_last4, owner_label, is_primary) VALUES (%s, '1111', 'Ana Prueba', FALSE), (%s, '9999', 'Titular', TRUE)", (WS_A, WS_A))
    rows = q(db, """INSERT INTO email_transaction_candidates (workspace_id, transaction_id, transaction_date, amount, transaction_type, card_owner, card_last4, status)
                    VALUES (%s, NULL, %s, 5000, 'expense', 'Ana Prueba', '1111', 'confirmed'), (%s, NULL, %s, 2500, 'expense', 'Ana Prueba', '1111', 'pending'),
                           (%s, NULL, %s, 9000, 'expense', 'Titular', '9999', 'confirmed'), (%s, NULL, %s, 4000, 'expense', 'Ana Prueba', '1111', 'confirmed')
                    RETURNING id""", (WS_A, TODAY, WS_A, TODAY, WS_A, TODAY, WS_B, TODAY))
    with database.get_connection() as conn:                       # what a scan/confirmation does in its own transaction
        service._receivables_follow_candidates(conn, WS_A, [{"card_last4": "1111", "transaction_date": TODAY}])
        conn.commit()
    [(rid,)] = q(db, "SELECT id FROM receivables WHERE workspace_id = %s", (WS_A,))
    assert stored(db, rid) == (5000.0, 0.0, 5000.0, "pending")   # holder card and other workspace excluded, pending not counted
    assert q(db, "SELECT count(*) FROM receivables WHERE workspace_id = %s", (WS_B,)) == [(0,)]
    with database.get_connection() as conn:                       # repeating it changes nothing
        service._receivables_follow_candidates(conn, WS_A, [{"card_last4": "1111", "transaction_date": TODAY}])
        conn.commit()
    assert q(db, "SELECT count(*) FROM receivable_entries") == [(1,)]
    service.decide_candidate(rows[0][0], "reject")               # the only confirmed purchase is rejected
    assert stored(db, rid) == (0.0, 0.0, 0.0, "completed")
    assert q(db, "SELECT is_archived, amount FROM receivable_entries") == [(True, 5000)]   # kept as history, not deleted


def test_a_movement_settles_at_most_once_and_only_if_it_is_money_in(db):
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    tx_id = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'SINPE', 20000, 'income', 'manual') RETURNING id", (WS_A, TODAY))[0][0]
    assert intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=tx_id, payment_date=TODAY)["status"] == "OK"
    assert intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=tx_id, payment_date=TODAY)["status"] == "DUPLICATE"
    other = intelligence.add_receivable_entry(person_name="Luis Ejemplo", amount=50000, description="", entry_kind="loan")["item"]["id"]
    assert intelligence.apply_receivable_payment(other, 20000, source_transaction_id=tx_id, payment_date=TODAY)["status"] == "DUPLICATE"
    expense = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'Supermercado', 20000, 'expense', 'manual') RETURNING id", (WS_A, TODAY))[0][0]
    assert intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=expense, payment_date=TODAY)["status"] == "ERROR"
    assert q(db, "SELECT count(*) FROM receivable_entries WHERE entry_type = 'payment'") == [(1,)]
    assert stored(db, rid)[2] == 30000.0 and stored(db, other)[2] == 50000.0


def test_concurrent_settlements_of_one_movement_apply_once_across_people(db):
    import threading
    from backend.auth.current_user import reset_current_user, set_current_user
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    rid2 = intelligence.add_receivable_entry(person_name="Luis Ejemplo", amount=50000, description="", entry_kind="loan")["item"]["id"]
    tx_id = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'SINPE', 20000, 'income', 'manual') RETURNING id", (WS_A, TODAY))[0][0]
    results, start = [], threading.Barrier(4)

    def settle(target):
        token = set_current_user({"id": 7, "account_id": "account-a", "workspace_id": WS_A, "role": "owner"})
        try:
            start.wait()
            results.append(intelligence.apply_receivable_payment(target, 20000, source_transaction_id=tx_id, payment_date=TODAY)["status"])
        finally:
            reset_current_user(token)

    # The same movement offered to two different people at once (different row locks).
    threads = [threading.Thread(target=settle, args=(target,)) for target in (rid, rid2, rid, rid2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["DUPLICATE", "DUPLICATE", "DUPLICATE", "OK"]
    assert q(db, "SELECT count(*) FROM receivable_entries WHERE entry_type = 'payment'") == [(1,)]
    assert sorted([stored(db, rid)[2], stored(db, rid2)[2]]) == [30000.0, 50000.0]


def test_settlements_wait_for_the_workspace_receivable_lock(db, admin_uri):
    """Every receivable writer serializes on one per-workspace lock (no check-then-insert race)."""
    import threading
    import time
    from backend.auth.current_user import reset_current_user, set_current_user
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    holder = psycopg2.connect(db.dsn)
    with holder.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"receivables:{WS_A}",))   # held until commit
    finished = []

    def settle():
        token = set_current_user({"id": 7, "account_id": "account-a", "workspace_id": WS_A, "role": "owner"})
        try:
            intelligence.apply_receivable_payment(rid, 1000, method="SINPE", payment_date=TODAY)
            finished.append(time.monotonic())
        finally:
            reset_current_user(token)

    worker = threading.Thread(target=settle)
    worker.start()
    time.sleep(0.5)
    released = time.monotonic()
    holder.commit()
    holder.close()
    worker.join(10)
    assert finished and finished[0] >= released


def test_automatic_match_never_turns_money_not_owed_into_a_collection(db, monkeypatch):
    """A payer-named income is a collection only up to what the person still owes."""
    from backend.core import database
    from backend.email_monitor import service
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=10000, description="", entry_kind="loan")["item"]["id"]
    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: WS_A)

    def confirm(amount):
        tx_id = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'SINPE recibido', %s, 'income', 'email_monitor') RETURNING id", (WS_A, TODAY, amount))[0][0]
        with database.get_connection() as conn:
            service._auto_apply_receivable_payment_from_candidate(conn, 7, tx_id, {"transaction_type": "income", "description": "SINPE recibido", "notes": "payer: Ana Prueba", "amount": amount, "transaction_date": TODAY})
            conn.commit()
        return q(db, "SELECT transaction_type, category, notes FROM transactions WHERE id = %s", (tx_id,))[0]

    assert confirm(15000)[0] == "income"                         # more than owed: left for the user to decide
    linked = confirm(10000)
    assert linked[0] == "receivable_payment" and linked[1] == "Cuentas por cobrar" and "tipo anterior: income" in linked[2]
    assert stored(db, rid) == (10000.0, 10000.0, 0.0, "completed")
    assert confirm(5000)[0] == "income"                          # settled person: a later SINPE is not a collection


def test_a_holder_card_never_becomes_a_receivable_even_if_not_flagged_primary(db):
    from backend.core import database
    from backend.finance import receivable_semantics

    q(db, "INSERT INTO card_aliases (workspace_id, card_last4, owner_label, relationship, is_primary) VALUES (%s, '2222', 'Titular', 'principal', FALSE), (%s, '1111', 'Ana Prueba', 'adicional', FALSE)", (WS_A, WS_A))
    q(db, "INSERT INTO email_transaction_candidates (workspace_id, transaction_id, transaction_date, amount, transaction_type, card_owner, card_last4, status) VALUES (%s, NULL, %s, 9000, 'expense', 'Titular', '2222', 'confirmed'), (%s, NULL, %s, 3000, 'expense', 'Ana Prueba', '1111', 'confirmed')", (WS_A, TODAY, WS_A, TODAY))
    with database.get_connection() as conn:
        receivable_semantics.mirror_additional_card_cycle(conn, WS_A)
        conn.commit()
    assert q(db, "SELECT person_name, pending_amount FROM receivables") == [("Ana Prueba", 3000)]


def test_only_received_money_settles_and_never_more_than_it_brought(db):
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]

    def movement(kind, amount=20000):
        return q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'mov', %s, %s, 'manual') RETURNING id", (WS_A, TODAY, amount, kind))[0][0]

    assert intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=movement("transfer"), payment_date=TODAY)["status"] == "ERROR"
    assert intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=movement("asset_sale"), payment_date=TODAY)["status"] == "ERROR"
    cash = movement("income")
    assert intelligence.apply_receivable_payment(rid, 18500, source_transaction_id=cash, method="non_cash_offset", payment_date=TODAY)["status"] == "ERROR"
    assert intelligence.apply_receivable_payment(rid, 25000, source_transaction_id=cash, payment_date=TODAY)["status"] == "ERROR"
    assert types(db) == {"transfer": 1, "asset_sale": 1, "income": 1}           # nothing was retyped
    assert stored(db, rid)[2] == 50000.0


def test_collections_and_asset_sales_raise_the_account_balance(db):
    from backend.finance import intelligence

    q(db, """CREATE TABLE account_balances (id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, account_name TEXT, bank_name TEXT, account_type TEXT,
             account_last4 TEXT, currency TEXT DEFAULT 'CRC', annual_interest_rate NUMERIC, last_reconciliation_difference NUMERIC, current_balance NUMERIC(14,2),
             balance_as_of TIMESTAMPTZ, source TEXT, include_in_net_worth BOOLEAN DEFAULT TRUE, is_active BOOLEAN DEFAULT TRUE, updated_at TIMESTAMPTZ DEFAULT NOW());
             CREATE TABLE exchange_rates (id BIGSERIAL PRIMARY KEY, workspace_id UUID, currency TEXT, exchange_rate NUMERIC, rate_date DATE);""")
    acc = q(db, "INSERT INTO account_balances (workspace_id, account_name, bank_name, current_balance, balance_as_of) VALUES (%s, 'Cuenta', 'Banco', 100000, NOW() - INTERVAL '1 day') RETURNING id", (WS_A,))[0][0]
    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    tx = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source, financial_account_id) VALUES (%s, %s, 'SINPE', 20000, 'income', 'manual', %s) RETURNING id", (WS_A, TODAY, acc))[0][0]
    q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, category, financial_account_id) VALUES (%s, %s, 'Venta de vehículo', 775000, 'asset_sale', 'Venta de activo', %s)", (WS_A, TODAY, acc))
    before = intelligence.list_account_balances()["items"][0]["calculated_balance"]
    intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=tx, payment_date=TODAY)
    after = intelligence.list_account_balances()["items"][0]["calculated_balance"]
    assert float(before) == float(after) == 895000.0             # retyping a collection never moves cash out of the account


def test_mail_duplicate_checks_survive_the_collection_retype(db):
    from backend.core import database
    from backend.email_monitor import service
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    other = intelligence.add_receivable_entry(person_name="Luis Ejemplo", amount=50000, description="", entry_kind="loan")["item"]["id"]
    tx = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'SINPE recibido', 20000, 'income', 'email_monitor') RETURNING id", (WS_A, TODAY))[0][0]
    intelligence.apply_receivable_payment(rid, 20000, source_transaction_id=tx, payment_date=TODAY)
    intelligence.apply_receivable_payment(other, 7000, method="SINPE", payment_date=TODAY)          # Luis's manual collection
    with database.get_connection() as conn:
        same = service._transaction_duplicate_match(conn, WS_A, {"transaction_date": TODAY, "amount": 20000, "transaction_type": "income", "description": "SINPE recibido"})
        foreign = service._existing_receivable_payment_match(conn, WS_A, {"transaction_type": "income", "transaction_date": TODAY, "amount": 7000, "description": "SINPE de Ana Prueba", "notes": "abono"})
    assert same == tx                                            # the same mail again is recognised after the retype
    assert foreign is None                                       # Ana's mail never matches Luis's manual collection


def test_unknown_spending_is_one_counted_bucket_in_the_monthly_summary(db):
    """Legacy empty categories and explicit "Sin categoría" are one row, counted in full."""
    from datetime import timedelta
    from backend.core import database
    from backend.user_product import free_service

    q(db, "CREATE TABLE expenses (id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, amount NUMERIC(14,2), category TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW())")
    q(db, "INSERT INTO expenses (workspace_id, amount, category) VALUES (%s, 1000, ''), (%s, 500, 'Comida')", (WS_A, WS_A))
    q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, category) VALUES (%s, %s, 'x', 2000, 'expense', 'Sin categoría')", (WS_A, TODAY))
    start = date.today().replace(day=1)
    with database.get_connection() as conn:
        rows = free_service._categories(conn, WS_A, start, start + timedelta(days=40))
    assert rows == [{"category": "Sin categoría", "amount": 3000.0}, {"category": "Comida", "amount": 500.0}]


def test_configured_cards_without_a_relationship_follow_their_primary_flag(monkeypatch):
    import json
    from backend.email_monitor import service

    monkeypatch.setenv("JARVIS_CARD_ALIASES", json.dumps([{"last4": "1111", "owner": "Ana Prueba"}, {"last4": "9999", "owner": "Titular", "is_primary": True}]))
    seen = []

    class Recorder:
        def execute(self, sql, params=()):
            seen.append(params)

    service._seed_default_card_aliases(Recorder(), 7, WS_A)
    assert [(p[2], p[4], p[5]) for p in seen] == [("1111", "adicional", False), ("9999", "principal", True)]


def test_a_linked_movement_settles_exactly_its_own_amount(db):
    from backend.finance import intelligence

    rid = intelligence.add_receivable_entry(person_name="Ana Prueba", amount=50000, description="", entry_kind="loan")["item"]["id"]
    tx = q(db, "INSERT INTO transactions (workspace_id, transaction_date, description, amount, transaction_type, source) VALUES (%s, %s, 'SINPE', 20000, 'income', 'manual') RETURNING id", (WS_A, TODAY))[0][0]
    assert intelligence.apply_receivable_payment(rid, 18500, source_transaction_id=tx, payment_date=TODAY)["status"] == "ERROR"
    assert types(db) == {"income": 1}                             # no part of the income silently vanished
