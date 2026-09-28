"""CRC/USD income and expenses on a real PostgreSQL, with the schema of 20260928110000.

A schema-faithful local copy, NOT a restored production copy: the identity
baseline, the ownership fixture tables with the production columns of
`salaries` and `expenses`, the ownership integrity migration (its guard triggers
sit on both tables) and the canonical original-currency migration of #280, which
is already on main and applied in production (its own protocol is tested in
test_income_expense_original_currency_migration_pg.py). All identities and
amounts are synthetic.

Covers the services on real rows: tenancy of the base currency, create and edit
in both directions, and concurrent edits and deletes.
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_financial_ownership_integrity_pg import (  # noqa: F401  (admin_uri is a fixture)
    IDENTITIES,
    MIGRATION as OWNERSHIP_MIGRATION,
    _add_phase_2a_fks,
    _create_database,
    _seed_identities,
    admin_uri,
)

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20260928110000_income_expense_original_currency.sql"
A, B = IDENTITIES["A"], IDENTITIES["B"]

# Production columns of the two tables that the ownership fixture does not carry
# (database/schema.sql + 20260925130000), and the account base currency.
PRODUCTION_SHAPE = """
ALTER TABLE accounts ADD COLUMN base_currency TEXT;
ALTER TABLE expenses ADD COLUMN expense_type TEXT NOT NULL DEFAULT 'variable', ADD COLUMN description TEXT;
CREATE TABLE salaries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    amount NUMERIC(14, 2) NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID,
    category TEXT NOT NULL DEFAULT 'Salario'
);
ALTER TABLE transactions ADD COLUMN original_amount NUMERIC(14, 2), ADD COLUMN original_currency TEXT,
    ADD COLUMN exchange_rate NUMERIC(14, 6);
CREATE TABLE payroll_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    event_type TEXT NOT NULL DEFAULT 'overtime',
    hours NUMERIC(8, 2) NOT NULL DEFAULT 1,
    multiplier NUMERIC(8, 4) NOT NULL DEFAULT 1.5,
    amount NUMERIC(14, 2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workspace_id UUID
);
"""


def _seed(cur) -> None:
    _seed_identities(cur)
    cur.execute(PRODUCTION_SHAPE)
    cur.execute("UPDATE accounts SET base_currency='CRC' WHERE id=%s", (A["account"],))
    cur.execute("UPDATE accounts SET base_currency='USD' WHERE id=%s", (B["account"],))
    for ident in (A, B):
        for n in range(1, 26):
            cur.execute("INSERT INTO salaries(user_id,amount,source,workspace_id,created_at) VALUES(%s,%s,'Synthetic pay',%s,NOW()-%s*INTERVAL '1 day')",
                        (ident["users"], Decimal(n * 1000) + Decimal("0.25"), ident["workspace"], n))
            cur.execute("INSERT INTO expenses(user_id,category,expense_type,description,amount,workspace_id) VALUES(%s,'Comida','variable','Synthetic',%s,%s)",
                        (ident["users"], Decimal(n * 37) + Decimal("0.10"), ident["workspace"]))
    _add_phase_2a_fks(cur)
    cur.execute(OWNERSHIP_MIGRATION.read_text(encoding="utf-8"))


@pytest.fixture
def db(admin_uri):  # noqa: F811
    uri, conn, drop = _create_database(admin_uri, _seed)
    try:
        yield {"uri": uri, "conn": conn}
    finally:
        drop()


def _connect(db, autocommit=True):
    conn = psycopg2.connect(db["uri"], application_name="Supavisor")
    conn.autocommit = autocommit
    return conn


def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()

def _apply(conn, path=MIGRATION):
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- services on real rows

@pytest.fixture
def app_db(db, monkeypatch):
    """The migration applied and the Users services pointed at this database."""
    from backend.core import database
    from backend.user_product import free_service, service

    _apply(db["conn"])
    monkeypatch.setattr(database, "DATABASE_URL", db["uri"])
    monkeypatch.setattr(service, "mark_applied", lambda _conn: None)
    from backend.auth.current_user import get_current_account_id

    legacy = {ident["account"]: ident["users"] for ident in IDENTITIES.values()}
    monkeypatch.setattr(service, "_legacy_financial_user_id", lambda: legacy[get_current_account_id()])
    return {**db, "service": service, "free_service": free_service}


def _as(ident, fn, *args):
    from backend.auth.current_user import reset_current_user, set_current_user

    token = set_current_user({"id": ident["allowed"], "account_id": ident["account"], "workspace_id": ident["workspace"], "role": "user"})
    try:
        return fn(*args)
    finally:
        reset_current_user(token)


def _row(db, table, row_id):
    return _one(db["conn"], f"SELECT amount,original_amount,original_currency,exchange_rate,workspace_id::text FROM {table} WHERE id=%s", (row_id,))


def test_each_account_converts_against_its_own_base_currency(app_db):
    from backend.user_product.models import ExpenseCreateRequest, IncomeCreateRequest

    svc = app_db["service"]
    crc = _as(A, svc.create_income, IncomeCreateRequest(amount=100, description="Synthetic", currency="USD", exchange_rate=505))
    usd = _as(B, svc.create_expense_entry, ExpenseCreateRequest(amount=50500, description="Synthetic", currency="CRC", exchange_rate=505))
    assert _row(app_db, "salaries", crc["id"]) == (Decimal("50500.00"), Decimal("100.00"), "USD", Decimal("505.000000"), A["workspace"])
    assert _row(app_db, "expenses", usd["id"]) == (Decimal("100.00"), Decimal("50500.00"), "CRC", Decimal("505.000000"), B["workspace"])
    # The rate history each account sees (the only source of the rate prefill) is its own.
    assert {row["workspace_id"] for row in _as(A, svc.list_income)} == {A["workspace"]}
    assert {row["workspace_id"] for row in _as(A, svc.list_expenses)} == {A["workspace"]}
    rates = lambda ident: {(row["origin"], row["original_currency"], str(row["exchange_rate"]))  # noqa: E731
                           for row in _as(ident, app_db["free_service"].list_free_movements) if row["exchange_rate"] is not None}
    assert {(origin, currency) for origin, currency, _rate in rates(A)} == {("salary", "USD")}
    assert {(origin, currency) for origin, currency, _rate in rates(B)} == {("expense", "CRC")}


def test_edits_in_both_directions_and_across_workspaces(app_db):
    from fastapi import HTTPException

    from backend.user_product.models import IncomeCreateRequest, MovementUpdateRequest

    svc, free = app_db["service"], app_db["free_service"]
    row_id = _as(A, svc.create_income, IncomeCreateRequest(amount=20000, description="Synthetic"))["id"]
    assert _row(app_db, "salaries", row_id)[:4] == (Decimal("20000.00"), None, None, None)

    _as(A, svc.update_income, row_id, IncomeCreateRequest(amount=100, currency="USD", exchange_rate=505))
    assert _row(app_db, "salaries", row_id)[:4] == (Decimal("50500.00"), Decimal("100.00"), "USD", Decimal("505.000000"))
    _as(A, free.update_free_movement, f"salary:{row_id}", MovementUpdateRequest(
        transaction_date="2026-09-20", description="Synthetic", amount=100, transaction_type="income", currency="USD", exchange_rate=510))
    assert _row(app_db, "salaries", row_id)[:4] == (Decimal("51000.00"), Decimal("100.00"), "USD", Decimal("510.000000"))
    _as(A, svc.update_income, row_id, IncomeCreateRequest(amount=51000, currency="CRC"))
    assert _row(app_db, "salaries", row_id)[:4] == (Decimal("51000.00"), None, None, None), "back to the base clears the originals"

    # B (USD base) cannot touch A's row by id, through either endpoint.
    with pytest.raises(HTTPException) as error:
        _as(B, svc.update_income, row_id, IncomeCreateRequest(amount=50500, currency="CRC", exchange_rate=505))
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        _as(B, free.update_free_movement, f"salary:{row_id}", MovementUpdateRequest(
            transaction_date="2026-09-20", description="x", amount=1, transaction_type="income"))
    assert error.value.status_code == 404
    assert _row(app_db, "salaries", row_id)[:4] == (Decimal("51000.00"), None, None, None)


def _in_thread(fn):
    result = {}

    def run():
        try:
            result["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - reported to the test
            result["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


def _hold_row(db, sql, params):
    """A second session that has changed the row and not yet committed."""
    other = _connect(db, autocommit=False)
    with other.cursor() as cur:
        cur.execute("SET LOCAL dincr.delete_workspace = %s", (A["workspace"],))
        cur.execute(sql, params)
    return other


def test_concurrent_edits_serialize_on_the_row_and_never_mix_amount_and_rate(app_db):
    from backend.user_product.models import ExpenseCreateRequest

    svc = app_db["service"]
    row_id = _as(A, svc.create_expense_entry, ExpenseCreateRequest(amount=100, currency="USD", exchange_rate=505))["id"]
    other = _hold_row(app_db, "UPDATE expenses SET amount=52000,original_amount=100,original_currency='USD',exchange_rate=520 WHERE id=%s", (row_id,))
    thread, result = _in_thread(lambda: _as(A, svc.update_expense, row_id, ExpenseCreateRequest(amount=200, currency="USD", exchange_rate=500)))
    time.sleep(1)
    assert thread.is_alive(), "the service edit waits for the row lock"
    other.commit()
    other.close()
    thread.join(20)
    assert "error" not in result
    amount, original, currency, rate, _ws = _row(app_db, "expenses", row_id)
    assert (amount, original, currency, rate) == (Decimal("100000.00"), Decimal("200.00"), "USD", Decimal("500.000000"))
    assert amount == (original * rate).quantize(Decimal("0.01")), "amount and rate always come from the same edit"


def test_an_edit_waiting_on_a_delete_reports_not_found(app_db):
    from fastapi import HTTPException

    from backend.user_product.models import IncomeCreateRequest

    svc = app_db["service"]
    row_id = _as(A, svc.create_income, IncomeCreateRequest(amount=100, currency="USD", exchange_rate=505))["id"]
    other = _hold_row(app_db, "DELETE FROM salaries WHERE id=%s AND workspace_id=%s", (row_id, A["workspace"]))
    thread, result = _in_thread(lambda: _as(A, svc.update_income, row_id, IncomeCreateRequest(amount=1, currency="USD", exchange_rate=505)))
    time.sleep(1)
    other.commit()
    other.close()
    thread.join(20)
    assert isinstance(result.get("error"), HTTPException) and result["error"].status_code == 404
    assert _one(app_db["conn"], "SELECT count(*) FROM salaries WHERE id=%s", (row_id,)) == (0,), "the edit never resurrects it"


@pytest.mark.parametrize("ident,kind,currency,typed,rate,stored", [
    # CRC account: CRC as typed, USD at the user's rate.
    ("A", "income", None, 18500, None, (Decimal("18500.00"), None, None, None)),
    ("A", "income", "USD", 100, 505, (Decimal("50500.00"), Decimal("100.00"), "USD", Decimal("505.000000"))),
    ("A", "expense", "CRC", 18500, None, (Decimal("18500.00"), None, None, None)),
    ("A", "expense", "USD", 21, 505, (Decimal("10605.00"), Decimal("21.00"), "USD", Decimal("505.000000"))),
    # USD account: USD as typed, CRC divided by the same rate (CRC per 1 USD).
    ("B", "income", "USD", 100, None, (Decimal("100.00"), None, None, None)),
    ("B", "income", "CRC", 50500, 505, (Decimal("100.00"), Decimal("50500.00"), "CRC", Decimal("505.000000"))),
    ("B", "expense", None, 21, None, (Decimal("21.00"), None, None, None)),
    ("B", "expense", "CRC", 10605, 505, (Decimal("21.00"), Decimal("10605.00"), "CRC", Decimal("505.000000"))),
])
def test_every_account_base_and_entry_currency(app_db, ident, kind, currency, typed, rate, stored):
    from backend.user_product.models import ExpenseCreateRequest, IncomeCreateRequest

    who = IDENTITIES[ident]
    model, create, table = ((IncomeCreateRequest, app_db["service"].create_income, "salaries") if kind == "income"
                            else (ExpenseCreateRequest, app_db["service"].create_expense_entry, "expenses"))
    row = _as(who, create, model(amount=typed, description="Synthetic", currency=currency, exchange_rate=rate))
    assert _row(app_db, table, row["id"]) == (*stored, who["workspace"])


@pytest.mark.parametrize("amount,currency,rate", [
    (20000000, "USD", 505),        # converted beyond the amount column
    (10000000000.00, None, None),  # one cent above the amount column, in the base currency
])
def test_an_entry_beyond_the_columns_is_a_422_and_writes_nothing(app_db, amount, currency, rate):
    from fastapi import HTTPException

    from backend.user_product.models import IncomeCreateRequest

    before = _one(app_db["conn"], "SELECT count(*) FROM salaries")
    with pytest.raises(HTTPException) as error:
        _as(A, app_db["service"].create_income, IncomeCreateRequest(amount=amount, description="Synthetic", currency=currency, exchange_rate=rate))
    assert error.value.status_code == 422
    assert _one(app_db["conn"], "SELECT count(*) FROM salaries") == before



@pytest.mark.parametrize("kind", ["salary", "expense"])
def test_a_movement_edited_back_to_the_base_clears_its_original(app_db, kind):
    """The movements screen's edit (free_service) clears the annotation, as the income/expense edit does."""
    from backend.user_product.models import ExpenseCreateRequest, IncomeCreateRequest, MovementUpdateRequest

    svc = app_db["service"]
    if kind == "salary":
        row = _as(A, svc.create_income, IncomeCreateRequest(amount=100, description="Synthetic", currency="USD", exchange_rate=505))
        table, transaction_type, category = "salaries", "income", "Otros ingresos"
    else:
        row = _as(A, svc.create_expense_entry, ExpenseCreateRequest(amount=21, description="Synthetic", currency="USD", exchange_rate=505))
        table, transaction_type, category = "expenses", "expense", "Comida"
    assert _row(app_db, table, row["id"])[2] == "USD"
    _as(A, app_db["free_service"].update_free_movement, f"{kind}:{row['id']}", MovementUpdateRequest(
        transaction_date="2026-09-20", description="Synthetic", amount=18500, transaction_type=transaction_type, category=category))
    assert _row(app_db, table, row["id"]) == (Decimal("18500.00"), None, None, None, A["workspace"])
