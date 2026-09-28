"""The income/expense original-currency migration (20260928110000) on a real PostgreSQL.

A schema-faithful local copy, NOT a restored production copy: the identity
baseline, the ownership fixture tables with the production columns of
`salaries` and `expenses`, and the ownership integrity migration (its guard
triggers sit on both tables). All identities and amounts are synthetic.

Migration only (no runtime code): preflight, apply, postflight, integrity, no
table rewrite, idempotency, the CHECK matrix, lock_timeout, failure atomicity,
manual rollback and reapply, and the application role's access to the new columns.
"""
from __future__ import annotations

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

from backend.tests.test_dincr_app_role_pg import WS_A, env  # noqa: F401,E402  (env is a fixture)

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20260928110000_income_expense_original_currency.sql"
ROLLBACK = ROOT / "database/rollback/20260928110000_income_expense_original_currency_rollback.sql"
A, B = IDENTITIES["A"], IDENTITIES["B"]
NEW_COLUMNS = ("original_amount", "original_currency", "exchange_rate")

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


def _all(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _apply(conn, path=MIGRATION):
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))


def _commented_query(marker: str) -> str:
    """The read-only query documented in the migration's comments after `marker`."""
    lines, grab = [], False
    for line in MIGRATION.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- ") and marker in line:
            grab = True
            continue
        if grab:
            if not line.startswith("--   "):
                if lines:
                    break
                continue  # the rest of the heading
            lines.append(line[5:])
    assert lines, marker
    return "\n".join(lines).rstrip().rstrip(";")


def _snapshot(conn) -> dict:
    """Existing data, digested column by column as it was before the migration."""
    state = {}
    for table, cols in (("salaries", "id,user_id,amount,source,created_at,workspace_id,category"),
                        ("expenses", "id,user_id,category,expense_type,description,amount,created_at,workspace_id")):
        state[table] = _one(conn, f"SELECT count(*), sum(amount), md5(string_agg(({cols})::text, '|' ORDER BY id)) FROM {table}")
        state[table + ":filenode"] = _one(conn, "SELECT pg_relation_filenode(%s)", (f"public.{table}",))[0]
    return state


def _columns(conn, table):
    return {name: (dtype, nullable, default) for name, dtype, nullable, default in _all(conn, """
        SELECT a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull, pg_get_expr(d.adbin, d.adrelid)
        FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
        WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped""", (f"public.{table}",))}


# --------------------------------------------------------------------------- migration protocol

def test_preflight_apply_postflight_keep_every_existing_row_and_do_not_rewrite(db):
    conn = db["conn"]
    assert _all(conn, _commented_query("Preflight (read-only)")) == [], "both tables exist, none of the columns does"
    before = _snapshot(conn)

    _apply(conn)

    assert _all(conn, _commented_query("Postflight (read-only)")) == []
    assert _snapshot(conn) == before, "no row, amount or column changed and neither table was rewritten"
    for table in ("salaries", "expenses"):
        cols = _columns(conn, table)
        assert cols["original_amount"] == ("numeric(14,2)", True, None)
        assert cols["original_currency"] == ("text", True, None)
        assert cols["exchange_rate"] == ("numeric(14,6)", True, None)
        assert _one(conn, f"SELECT count(*) FROM {table} WHERE original_amount IS NOT NULL OR original_currency IS NOT NULL OR exchange_rate IS NOT NULL") == (0,)
        assert _one(conn, "SELECT convalidated FROM pg_constraint WHERE conname=%s", (f"{table}_original_currency_check",)) == (True,)


def test_reapplying_is_a_no_op(db):
    conn = db["conn"]
    _apply(conn)
    before = _snapshot(conn)
    _apply(conn)
    assert _snapshot(conn) == before
    assert _one(conn, "SELECT count(*) FROM pg_constraint WHERE conname LIKE '%%_original_currency_check'") == (2,)
    assert _all(conn, _commented_query("Postflight (read-only)")) == []


CHECK_CASES = [
    ((None, None, None), True),
    ((100, "USD", 505), True),
    ((50500, "CRC", 505), True),
    ((100, "USD", None), False),        # all-or-nothing: a CHECK that evaluates to NULL passes,
    ((None, "USD", 505), False),        # so each column needs its own IS NOT NULL
    ((100, None, 505), False),
    ((None, None, 505), False),
    ((100, "EUR", 1.1), False),         # CRC|USD only
    ((100, "usd", 505), False),
    ((0, "USD", 505), False),           # positive amount and rate
    ((-1, "USD", 505), False),
    ((100, "USD", 0), False),
]


def test_the_check_is_all_or_nothing_crc_usd_and_positive(db):
    conn = db["conn"]
    _apply(conn)
    for table, insert in (("salaries", "INSERT INTO salaries(user_id,amount,source,workspace_id,original_amount,original_currency,exchange_rate) VALUES(%s,1,'x',%s,%s,%s,%s)"),
                          ("expenses", "INSERT INTO expenses(user_id,category,amount,workspace_id,original_amount,original_currency,exchange_rate) VALUES(%s,'x',1,%s,%s,%s,%s)")):
        for values, ok in CHECK_CASES:
            params = (A["users"], A["workspace"], *values)
            if ok:
                _one(conn, insert + " RETURNING id", params)
            else:
                with pytest.raises(psycopg2.errors.CheckViolation, match=f"{table}_original_currency_check"):
                    _one(conn, insert + " RETURNING id", params)


def test_a_lock_it_cannot_get_within_lock_timeout_applies_nothing(db):
    conn = db["conn"]
    holder = _connect(db, autocommit=False)
    try:
        _one(holder, "SELECT count(*) FROM expenses")  # ACCESS SHARE held by an open transaction
        started = time.monotonic()
        with pytest.raises(psycopg2.errors.LockNotAvailable):
            _apply(conn)
        assert time.monotonic() - started < 30, "bounded by the migration's lock_timeout (5 s)"
    finally:
        holder.rollback()
        holder.close()
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")  # the failed script left its transaction aborted
    for table in ("salaries", "expenses"):
        assert not set(NEW_COLUMNS) & set(_columns(conn, table)), f"{table}: all or nothing"


def test_a_failure_after_the_first_table_rolls_back_the_first_table_too(db):
    conn = db["conn"]
    # Drift: someone added one column to expenses by hand and stored a value the CHECK refuses.
    _one(conn, "ALTER TABLE expenses ADD COLUMN original_currency TEXT; UPDATE expenses SET original_currency='EUR' WHERE id=(SELECT min(id) FROM expenses) RETURNING id")
    assert _all(conn, _commented_query("Preflight (read-only)")) != [], "the preflight reports the drift before anything runs"
    with pytest.raises(psycopg2.errors.CheckViolation):
        _apply(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")
    assert not set(NEW_COLUMNS) & set(_columns(conn, "salaries")), "salaries was altered first and is rolled back"
    assert set(_columns(conn, "expenses")) & set(NEW_COLUMNS) == {"original_currency"}, "only the hand-made column remains"


def test_manual_rollback_keeps_amounts_snapshots_the_originals_and_allows_reapply(db):
    conn = db["conn"]
    _apply(conn)
    _one(conn, "UPDATE salaries SET amount=50500,original_amount=100,original_currency='USD',exchange_rate=505 WHERE id=(SELECT min(id) FROM salaries WHERE workspace_id=%s) RETURNING id", (A["workspace"],))
    before = _snapshot(conn)

    _apply(conn, ROLLBACK)

    for table in ("salaries", "expenses"):
        assert not set(NEW_COLUMNS) & set(_columns(conn, table))
    after = _snapshot(conn)
    assert {k: v for k, v in after.items() if not k.endswith(":filenode")} == {k: v for k, v in before.items() if not k.endswith(":filenode")}
    assert _all(conn, "SELECT source_table,original_amount,original_currency,exchange_rate FROM income_expense_original_currency_rollback_snapshot") == [
        ("salaries", Decimal("100.00"), "USD", Decimal("505.000000"))]
    _apply(conn, ROLLBACK)  # a second run changes nothing
    _apply(conn)
    assert _all(conn, _commented_query("Postflight (read-only)")) == []


# --------------------------------------------------------------------------- the application role

def test_the_application_role_reads_and_writes_the_new_columns_with_its_table_grants(env):  # noqa: F811
    """dincr_app's table-level privileges (20260926150000) cover columns added later: no new grant is needed."""
    owner, app = env["owner"], env["as_app"]()
    owner.execute(MIGRATION.read_text(encoding="utf-8"))
    for table in ("salaries", "expenses"):
        owner.execute("""SELECT count(*) FROM information_schema.column_privileges
                         WHERE table_schema = 'public' AND table_name = %s AND column_name = ANY(%s)
                           AND grantee IN ('anon', 'authenticated')""", (table, list(NEW_COLUMNS)))
        assert owner.fetchone() == (0,)
        owner.execute("""SELECT c, p FROM unnest(%s::text[]) c, unnest(ARRAY['SELECT', 'INSERT', 'UPDATE']) p
                         WHERE NOT has_column_privilege('dincr_app', %s, c, p)""", (list(NEW_COLUMNS), f"public.{table}"))
        assert owner.fetchall() == [], table
        # The required columns of each table on this setup (expenses: the ownership fixture, where
        # 11 is WS_A's legacy identity; salaries: the role test's stand-in table).
        required = {"expenses": {"user_id": 11, "category": "Synthetic", "amount": 1}, "salaries": {}}[table]
        owner_columns, owner_values = "".join(f"{c}, " for c in required), tuple(required.values())
        app.execute(f"""INSERT INTO public.{table}({owner_columns}workspace_id, original_amount, original_currency, exchange_rate)
                        VALUES ({"%s, " * len(owner_values)}%s, 100, 'USD', 505) RETURNING id""", (*owner_values, WS_A))
        row_id = app.fetchone()[0]
        app.execute(f"UPDATE public.{table} SET original_amount = 200 WHERE id = %s", (row_id,))
        app.execute(f"SELECT original_amount, original_currency, exchange_rate FROM public.{table} WHERE id = %s", (row_id,))
        assert app.fetchone() == (Decimal("200.00"), "USD", Decimal("505.000000"))
        with pytest.raises(psycopg2.errors.CheckViolation):
            app.execute(f"INSERT INTO public.{table}({owner_columns}workspace_id, original_currency) "
                        f"VALUES ({'%s, ' * len(owner_values)}%s, 'USD')", (*owner_values, WS_A))


def test_the_rollback_snapshot_is_invisible_to_the_application_role(env):  # noqa: F811
    """The data export lists tables with workspace_id from information_schema as dincr_app: the
    rollback's snapshot (workspace_id, no grant) must not appear there, nor be readable."""
    owner, app = env["owner"], env["as_app"]()
    owner.execute(MIGRATION.read_text(encoding="utf-8"))
    owner.execute(ROLLBACK.read_text(encoding="utf-8"))
    app.execute("""SELECT count(*) FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = 'income_expense_original_currency_rollback_snapshot'""")
    assert app.fetchone() == (0,)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        app.execute("SELECT count(*) FROM public.income_expense_original_currency_rollback_snapshot")
    for role in ("anon", "authenticated"):
        owner.execute("SELECT has_table_privilege(%s, 'public.income_expense_original_currency_rollback_snapshot', 'SELECT')", (role,))
        assert owner.fetchone() == (False,)
