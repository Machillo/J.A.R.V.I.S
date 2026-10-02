"""Payroll receipts on PostgreSQL, connected as the application role (dincr_app).

Built on the role test's environment (identity baseline, ownership guards, dincr_app) plus
20261003120000_payroll_receipts. A receipt explains a salary deposit and never adds income,
spending, balance or debt; the database enforces its invariants. Synthetic data only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.tests.test_dincr_app_role_pg import WS_A, WS_B, env  # noqa: F401  (fixture)

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2] / "database"
MIGRATION = ROOT / "migrations/20261003120000_payroll_receipts.sql"
ROLLBACK = ROOT / "rollback/20261003120000_payroll_receipts_rollback.sql"

RECEIPT = """COMPROBANTE DE PAGO
| EMPRESA EJEMPLO, S.A. | PLANILLA SEMANAL COLONES |
| COMPROBANTE DE PAGO PERIODO: 203002 DEL 06/01/2030 AL 12/01/2030 |
| FECHA EMISIÓN: 17/01/2030 |
| <<INGRESOS>> |
| HORAS REGULARES TRABAJADAS (40 Horas) | ¢ 40,000.00 |
| TIEMPO EXTRA- OT1 (4 Horas) | ¢ 6,000.00 |
| PAGO FERIADO | ¢ 8,000.00 |
| VACACION | ¢ 5,000.00 |
| BONO POR METRICAS | ¢ 2,500.00 |
| <<DESCUENTOS>> |
| CCSS 10.83% | ¢ 6,660.45 |
| APORTE OBRERO 5% ASOCIACION SOLIDARISTA | ¢ 3,075.00 |
| PRESTAMO BANCO EJEMPLO | ¢ 9,000.00 |
| TOTAL INGRESOS: | ¢ 61,500.00 |
| TOTAL DESCUENTOS: | ¢ 18,735.45 |
| NETO A PAGAR: ¢ 42,764.55 |
"""
NET = 42764.55


def weekly(period_from: str, period_to: str, issued: str, net_text: str = "42,764.55") -> str:
    return (RECEIPT.replace("DEL 06/01/2030 AL 12/01/2030", f"DEL {period_from} AL {period_to}")
            .replace("FECHA EMISIÓN: 17/01/2030", f"FECHA EMISIÓN: {issued}"))


@pytest.fixture
def db(env, monkeypatch):
    """The migrated database; `app` is a dincr_app connection, and backend.core.database uses dincr_app."""
    from backend.core import database
    from backend.auth.current_user import reset_current_user, set_current_user

    owner = env["owner"]
    owner.execute(MIGRATION.read_text(encoding="utf-8"))
    info = owner.connection.info
    app = psycopg2.connect(host=info.host, port=info.port, dbname=info.dbname, user="dincr_app")
    app.autocommit = True
    uri = (f"postgresql://dincr_app@/{info.dbname}?host={info.host}&port={info.port}" if info.host.startswith("/")
           else f"postgresql://dincr_app@{info.host}:{info.port}/{info.dbname}")
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    database.close_idle_connections()
    token = set_current_user({"id": 11, "account_id": "a", "workspace_id": WS_A, "role": "owner"})
    try:
        yield {"owner": owner, "app": app.cursor(), "app_conn": app}
    finally:
        reset_current_user(token)
        database.close_idle_connections()
        app.close()


def tx(cur, ws, day, amount, kind="income", description="Depósito", category=None, notes=None):
    legacy = 11 if ws == WS_A else 12   # the workspace owner's legacy id (still required by the fixture)
    cur.execute("""INSERT INTO transactions (user_id, workspace_id, transaction_date, description, amount, transaction_type, category, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""", (legacy, ws, day, description, amount, kind, category, notes))
    return cur.fetchone()[0]


def raw_receipt(cur, ws, *, net=100.0, gross=150.0, deductions=50.0, status="PAYROLL_ONLY", transaction_id=None, period=("2030-01-06", "2030-01-12"),
                lines=True):
    """Insert a receipt (and lines that add up) in one transaction; returns its id."""
    cur.execute("BEGIN")
    cur.execute("""INSERT INTO payroll_receipts (workspace_id, transaction_id, period_start, period_end, issue_date, gross, deductions, net,
                                                 match_status, source) VALUES (%s, %s, %s, %s, '2030-01-17', %s, %s, %s, %s, 'test') RETURNING id""",
                (ws, transaction_id, period[0], period[1], gross, deductions, net, status))
    rid = cur.fetchone()[0]
    if lines:
        cur.execute("INSERT INTO payroll_receipt_lines (workspace_id, receipt_id, section, kind, label, amount) VALUES (%s, %s, 'income', 'ordinary', 'base', %s)", (ws, rid, gross))
        cur.execute("INSERT INTO payroll_receipt_lines (workspace_id, receipt_id, section, kind, label, amount) VALUES (%s, %s, 'deduction', 'social_security', 'ss', %s)", (ws, rid, deductions))
    cur.execute("COMMIT")
    return rid


def fails(cur, fn):
    try:
        fn()
    except psycopg2.Error:
        try:
            cur.execute("ROLLBACK")
        except psycopg2.Error:
            pass
        return True
    return False


# ---------------------------------------------------------------- database invariants

def test_a_valid_receipt_is_stored_and_its_totals_must_add_up(db):
    app = db["app"]
    rid = raw_receipt(app, WS_A)
    app.execute("SELECT match_status, gross - deductions - net FROM payroll_receipts WHERE id = %s", (rid,))
    assert app.fetchone() == ("PAYROLL_ONLY", 0)
    # gross - deductions != net is rejected
    assert fails(app, lambda: raw_receipt(app, WS_A, net=99.0, period=("2030-02-01", "2030-02-07")))
    # lines that do not add up are rejected at commit
    def bad_lines():
        app.execute("BEGIN")
        app.execute("""INSERT INTO payroll_receipts (workspace_id, period_start, period_end, gross, deductions, net, source)
                       VALUES (%s, '2030-03-01', '2030-03-07', 150, 50, 100, 'test') RETURNING id""", (WS_A,))
        r = app.fetchone()[0]
        app.execute("INSERT INTO payroll_receipt_lines (workspace_id, receipt_id, section, kind, label, amount) VALUES (%s, %s, 'income', 'ordinary', 'x', 140)", (WS_A, r))
        app.execute("COMMIT")
    assert fails(app, bad_lines)


def test_matched_needs_an_income_of_exactly_the_net_and_is_one_to_one(db):
    app = db["app"]
    wrong = tx(app, WS_A, "2030-01-17", 99.0)
    expense = tx(app, WS_A, "2030-01-17", 100.0, kind="expense")
    good = tx(app, WS_A, "2030-01-17", 100.0)
    assert fails(app, lambda: raw_receipt(app, WS_A, status="MATCHED", transaction_id=wrong))
    assert fails(app, lambda: raw_receipt(app, WS_A, status="MATCHED", transaction_id=expense))
    assert fails(app, lambda: raw_receipt(app, WS_A, status="MATCHED"))                       # MATCHED without a link
    raw_receipt(app, WS_A, status="MATCHED", transaction_id=good)
    # the same transaction cannot explain a second receipt
    assert fails(app, lambda: raw_receipt(app, WS_A, status="MATCHED", transaction_id=good, period=("2030-01-13", "2030-01-19")))


def test_links_never_cross_workspaces(db):
    app = db["app"]
    other_tx = tx(app, WS_B, "2030-01-17", 100.0)
    assert fails(app, lambda: raw_receipt(app, WS_A, status="MATCHED", transaction_id=other_tx))
    db["owner"].execute("INSERT INTO debts (user_id, name, debt_type, total_amount, remaining_amount, monthly_payment, workspace_id) "
                        "VALUES (12, 'Banco Otro', 'other', 1000, 800, 100, %s) RETURNING id", (WS_B,))
    other_debt = db["owner"].fetchone()[0]

    def foreign_debt_line():
        app.execute("BEGIN")
        app.execute("""INSERT INTO payroll_receipts (workspace_id, period_start, period_end, gross, deductions, net, source)
                       VALUES (%s, '2030-04-01', '2030-04-07', 150, 50, 100, 'test') RETURNING id""", (WS_A,))
        r = app.fetchone()[0]
        app.execute("INSERT INTO payroll_receipt_lines (workspace_id, receipt_id, section, kind, label, amount) VALUES (%s, %s, 'income', 'ordinary', 'x', 150)", (WS_A, r))
        app.execute("INSERT INTO payroll_receipt_lines (workspace_id, receipt_id, section, kind, label, amount, debt_id) VALUES (%s, %s, 'deduction', 'loan_repayment', 'y', 50, %s)", (WS_A, r, other_debt))
        app.execute("COMMIT")
    assert fails(app, foreign_debt_line)


def test_the_same_receipt_is_stored_once(db):
    app = db["app"]
    raw_receipt(app, WS_A)
    assert fails(app, lambda: raw_receipt(app, WS_A))                                       # same workspace, period, gross, net
    raw_receipt(app, WS_B)                                                                  # another workspace is independent


def test_a_changed_or_deleted_deposit_leaves_the_receipt_unresolved_not_matched(db):
    app, owner = db["app"], db["owner"]
    t1 = tx(app, WS_A, "2030-01-17", 100.0)
    r1 = raw_receipt(app, WS_A, status="MATCHED", transaction_id=t1)
    app.execute("UPDATE transactions SET amount = 90 WHERE id = %s", (t1,))
    app.execute("SELECT match_status, transaction_id FROM payroll_receipts WHERE id = %s", (r1,))
    assert app.fetchone() == ("UNRESOLVED", t1)
    t2 = tx(app, WS_A, "2030-01-24", 100.0)
    r2 = raw_receipt(app, WS_A, status="MATCHED", transaction_id=t2, period=("2030-01-13", "2030-01-19"))
    owner.execute("SELECT set_config('dincr.delete_workspace', %s, false)", (WS_A,))
    owner.execute("DELETE FROM transactions WHERE id = %s", (t2,))
    app.execute("SELECT match_status, transaction_id FROM payroll_receipts WHERE id = %s", (r2,))
    assert app.fetchone() == ("UNRESOLVED", None)


def test_the_application_role_reads_and_writes_receipts_but_never_deletes_them(db):
    app = db["app"]
    rid = raw_receipt(app, WS_A)
    assert fails(app, lambda: app.execute("DELETE FROM payroll_receipts WHERE id = %s", (rid,)))
    owner = db["owner"]
    owner.execute("SELECT tgname FROM pg_trigger WHERE tgrelid = 'public.payroll_receipts'::regclass AND NOT tgisinternal ORDER BY 1")
    triggers = {r[0] for r in owner.fetchall()}
    assert {"trg_payroll_receipts_delete_guard", "trg_payroll_receipts_truncate_guard", "trg_payroll_receipts_workspace_move_guard"} <= triggers
    owner.execute("SELECT relrowsecurity FROM pg_class WHERE oid IN ('public.payroll_receipts'::regclass, 'public.payroll_receipt_lines'::regclass)")
    assert all(r[0] for r in owner.fetchall())


def test_migration_reapplies_and_rolls_back_only_when_empty(db):
    owner = db["owner"]
    owner.execute(MIGRATION.read_text(encoding="utf-8"))                                     # idempotent re-apply
    owner.execute("SELECT count(*) FROM public.dincr_delete_guard_tables() WHERE table_name LIKE 'payroll_receipt%'")
    assert owner.fetchone()[0] == 2
    raw_receipt(db["app"], WS_A)
    assert fails(owner, lambda: owner.execute(ROLLBACK.read_text(encoding="utf-8")))      # refuses while receipts exist
    owner.execute("SELECT set_config('dincr.delete_workspace', %s, false)", (WS_A,))
    owner.execute("DELETE FROM payroll_receipts")
    owner.execute(ROLLBACK.read_text(encoding="utf-8"))
    owner.execute("SELECT to_regclass('public.payroll_receipts'), (SELECT count(*) FROM public.dincr_delete_guard_tables() WHERE table_name LIKE 'payroll_receipt%')")
    assert owner.fetchone() == (None, 0)
    owner.execute(MIGRATION.read_text(encoding="utf-8"))                                     # and re-applies cleanly
    owner.execute("SELECT to_regclass('public.payroll_receipts') IS NOT NULL")
    assert owner.fetchone()[0] is True


# ---------------------------------------------------------------- module: record, match, read

def record(text, key=None):
    from backend.core.database import get_connection
    from backend.email_monitor.payroll_statement import parse_payroll_receipt
    from backend.finance import payroll_receipts
    with get_connection() as conn:
        out = payroll_receipts.record_receipt(conn, workspace_id=WS_A, parsed=parse_payroll_receipt(text), source="mail_receipt", source_key=key)
        conn.commit()
    return out


def snapshot(owner, ws=WS_A):
    owner.execute("SELECT count(*), coalesce(sum(amount), 0) FROM transactions WHERE workspace_id = %s", (ws,))
    txs = owner.fetchone()
    owner.execute("SELECT count(*) FROM debt_payments")
    dps = owner.fetchone()
    owner.execute("SELECT md5(string_agg(d::text, ',' ORDER BY id)) FROM debts d")
    return txs, dps, owner.fetchone()


def test_a_receipt_matches_the_deposit_that_names_its_period_and_never_adds_income(db):
    owner = db["owner"]
    dep = tx(db["app"], WS_A, "2030-01-17", NET, description="Planilla 06/01/2030 12/01/2030", category="Salario")
    tx(db["app"], WS_A, "2030-01-17", NET, description="Transferencia recibida")               # same amount, no period: ignored
    before = snapshot(owner)
    out = record(RECEIPT, key="m1")
    assert out["status"] == "RECORDED" and out["match_status"] == "MATCHED" and out["transaction_id"] == dep
    assert snapshot(owner) == before                                                          # no income, expense, debt payment or debt change


def test_amount_and_date_alone_are_only_a_possible_match_until_a_person_confirms(db):
    from backend.core.database import get_connection
    from backend.finance import payroll_receipts
    a = tx(db["app"], WS_A, "2030-01-17", NET, description="Depósito")
    b = tx(db["app"], WS_A, "2030-01-18", NET, description="Depósito")
    out = record(RECEIPT, key="m2")
    assert out["match_status"] == "POSSIBLE_MATCH" and sorted(out["candidates"]) == sorted([a, b])
    with get_connection() as conn:
        assert payroll_receipts.link_receipt(conn, workspace_id=WS_A, receipt_id=out["receipt_id"], transaction_id=b)["status"] == "OK"
        conn.commit()
    db["owner"].execute("SELECT match_status, transaction_id FROM payroll_receipts WHERE id = %s", (out["receipt_id"],))
    assert db["owner"].fetchone() == ("MATCHED", b)


def test_two_payroll_deposits_of_the_same_amount_are_never_guessed(db):
    tx(db["app"], WS_A, "2030-01-17", NET, description="Salario", category="Salario")
    tx(db["app"], WS_A, "2030-01-19", NET, description="Salario", category="Salario")
    assert record(RECEIPT, key="m3")["match_status"] == "POSSIBLE_MATCH"


def test_a_receipt_waits_for_its_deposit_and_matches_when_it_arrives(db):
    from backend.core.database import get_connection
    from backend.finance import payroll_receipts
    out = record(RECEIPT, key="m4")
    assert out["match_status"] == "PAYROLL_ONLY"
    dep = tx(db["app"], WS_A, "2030-01-17", NET, description="Planilla 06/01/2030 12/01/2030")
    with get_connection() as conn:
        payroll_receipts.match_pending_for_transaction(conn, workspace_id=WS_A, transaction_id=dep)
        conn.commit()
    db["owner"].execute("SELECT match_status, transaction_id FROM payroll_receipts WHERE id = %s", (out["receipt_id"],))
    assert db["owner"].fetchone() == ("MATCHED", dep)


def test_weekly_receipts_of_one_month_each_match_their_own_deposit(db):
    weeks = [("06/01/2030", "12/01/2030", "17/01/2030", "2030-01-17"), ("13/01/2030", "19/01/2030", "24/01/2030", "2030-01-24"),
             ("20/01/2030", "26/01/2030", "31/01/2030", "2030-01-31")]
    deposits = [tx(db["app"], WS_A, day, NET, description=f"Planilla {f} {t}", category="Salario") for f, t, _, day in weeks]
    results = [record(weekly(f, t, issued), key=f"w{i}") for i, (f, t, issued, _) in enumerate(weeks)]
    assert [r["match_status"] for r in results] == ["MATCHED"] * 3
    assert [r["transaction_id"] for r in results] == deposits                                 # each its own deposit, none twice


def test_duplicate_and_inconsistent_receipts(db):
    assert record(RECEIPT, key="d1")["status"] == "RECORDED"
    assert record(RECEIPT, key="d1")["status"] == "DUPLICATE"                                  # same message
    assert record(RECEIPT, key="d2")["status"] == "DUPLICATE"                                  # same receipt from another message
    assert record(RECEIPT.replace("NETO A PAGAR: ¢ 42,764.55", "NETO A PAGAR: ¢ 40,000.00"), key="d3")["status"] == "REJECTED_INCONSISTENT"


def test_composition_and_loan_deduction_link_to_the_debt_without_paying_it(db):
    from backend.core.database import get_connection
    from backend.finance import payroll_receipts
    owner = db["owner"]
    owner.execute("INSERT INTO debts (user_id, name, debt_type, total_amount, remaining_amount, monthly_payment, workspace_id) "
                  "VALUES (11, 'Banco Ejemplo', 'other', 1000, 800, 100, %s) RETURNING id", (WS_A,))
    debt = owner.fetchone()[0]
    tx(db["app"], WS_A, "2030-01-17", NET, description="Planilla 06/01/2030 12/01/2030", category="Salario")
    before = snapshot(owner)
    rid = record(RECEIPT, key="c1")["receipt_id"]
    with get_connection() as conn:
        item = payroll_receipts.get_receipt(conn, workspace_id=WS_A, receipt_id=rid)
    assert item["income"]["ordinary"]["amount"] == 40000.0 and item["income"]["ordinary"]["hours"] == 40.0
    assert item["income"]["overtime"] == {"amount": 6000.0, "hours": 4.0, "lines": item["income"]["overtime"]["lines"]}
    assert item["income"]["holiday_paid"]["amount"] == 8000.0 and item["income"]["vacation"]["amount"] == 5000.0
    assert item["income"]["bonus"]["amount"] == 2500.0 and item["gross"] == 61500.0
    assert item["deductions"]["social_security"]["amount"] == 6660.45 and item["deductions"]["association"]["amount"] == 3075.0
    loan = item["deductions"]["loan_repayment"]
    assert loan["amount"] == 9000.0 and loan["lines"][0]["debt_id"] == debt
    assert item["net"] == NET and item["deposit"]["net_equals_deposit"] is True and item["deductions_create_movements"] is False
    assert snapshot(owner) == before                                                          # no debt payment, no debt change, no movement


def test_reading_receipts_writes_nothing(db):
    from backend.core import database
    from backend.finance import payroll_receipts
    record(RECEIPT, key="r1")
    owner = db["owner"]
    owner.execute("SELECT md5(string_agg(r::text, ',')) FROM payroll_receipts r")
    before = owner.fetchone()
    owner.execute("SELECT current_database()")
    name = owner.fetchone()[0]
    owner.execute(f'ALTER DATABASE "{name}" SET default_transaction_read_only = on')
    database.close_idle_connections()
    try:
        with database.get_connection() as conn:
            listed = payroll_receipts.list_receipts(conn, workspace_id=WS_A)
            payroll_receipts.get_receipt(conn, workspace_id=WS_A, receipt_id=listed[0]["id"])
    finally:
        owner.execute(f'ALTER DATABASE "{name}" RESET default_transaction_read_only')
        database.close_idle_connections()
    owner.execute("SELECT md5(string_agg(r::text, ',')) FROM payroll_receipts r")
    assert owner.fetchone() == before and len(listed) == 1
