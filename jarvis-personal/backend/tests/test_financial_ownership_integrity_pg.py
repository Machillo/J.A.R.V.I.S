"""Financial ownership integrity against a real PostgreSQL.

Uses DINCR_TEST_POSTGRES_URL (a server where the test may CREATE DATABASE) or,
when absent, an embedded server from the `pgserver` package. CI sets
DINCR_REQUIRE_PG_TESTS=1 so these tests fail instead of silently skipping.

All identities and amounts are synthetic. The fixture reproduces the two legacy
id spaces of user_id (allowed_users.id and users.id) with deliberate collisions:
account A's users.id equals account B's allowed_users.id.

DINCR_TEST_POSTGRES_URL must point at a disposable server: the tests create
databases and the anon/authenticated roles on it.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "database/baseline/v1_identity_ownership.sql"
FIXTURE = Path(__file__).resolve().parent / "fixtures/ownership_financial_tables.sql"
MIGRATION = ROOT / "database/migrations/20260925140000_financial_ownership_integrity.sql"

WS_A = "00000000-0000-4000-8000-00000000000a"
WS_B = "00000000-0000-4000-8000-00000000000b"
WS_C = "00000000-0000-4000-8000-00000000000c"
ACC_A = "00000000-0000-4000-8000-0000000000a1"
ACC_B = "00000000-0000-4000-8000-0000000000b1"
ACC_C = "00000000-0000-4000-8000-0000000000c1"
MISSING_WS = "00000000-0000-4000-8000-0000000000ff"

# allowed_users ids and users ids per account; users ids collide across spaces.
IDENTITIES = {
    "A": {"account": ACC_A, "workspace": WS_A, "email": "a@example.test", "allowed": 11, "users": 12},
    "B": {"account": ACC_B, "workspace": WS_B, "email": "b@example.test", "allowed": 12, "users": 13},
    "C": {"account": ACC_C, "workspace": WS_C, "email": "c@example.test", "allowed": 13, "users": 14},
}


def _admin_uri(data_dir: Path) -> str:
    url = os.getenv("DINCR_TEST_POSTGRES_URL", "").strip()
    if url:
        return url
    try:
        import pgserver
    except ImportError:
        if os.getenv("DINCR_REQUIRE_PG_TESTS") == "1":
            pytest.fail("PostgreSQL tests are required but neither DINCR_TEST_POSTGRES_URL nor pgserver is available.")
        pytest.skip("No PostgreSQL available (set DINCR_TEST_POSTGRES_URL or install pgserver).")
    return pgserver.get_server(data_dir, cleanup_mode="delete").get_uri()


@pytest.fixture(scope="module")
def admin_uri(tmp_path_factory):
    return _admin_uri(tmp_path_factory.mktemp("pgserver"))


def _with_database(uri: str, name: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(uri)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


def _create_database(admin_uri: str, seed) -> tuple[str, "psycopg2.extensions.connection", callable]:
    name = f"ownership_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not cur.fetchone():
                cur.execute(f'CREATE ROLE "{role}" NOLOGIN')
        cur.execute(f'CREATE DATABASE "{name}"')
    uri = _with_database(admin_uri, name)
    # Fixture connections act as the application (pooler connection name).
    conn = psycopg2.connect(uri, application_name="Supavisor")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(BASELINE.read_text(encoding="utf-8"))
        cur.execute(FIXTURE.read_text(encoding="utf-8"))
        seed(cur)

    def drop():
        conn.close()
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()

    return uri, conn, drop


@pytest.fixture
def db(admin_uri):
    """A fresh database with the identity baseline, the fixture tables and seed rows."""
    uri, conn, drop = _create_database(admin_uri, _seed_identities)
    try:
        yield {"uri": uri, "conn": conn}
    finally:
        drop()


def _seed_identities(cur) -> None:
    for ident in IDENTITIES.values():
        cur.execute(
            "INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')",
            (ident["allowed"], ident["email"]),
        )
        cur.execute(
            "INSERT INTO users(id,email,name,country,timezone) VALUES(%s,%s,'Synthetic','Nowhere','UTC')",
            (ident["users"], ident["email"]),
        )
        cur.execute(
            "INSERT INTO accounts(id,legacy_allowed_user_id,primary_email) VALUES(%s,%s,%s)",
            (ident["account"], ident["allowed"], ident["email"]),
        )
        cur.execute(
            "INSERT INTO workspaces(id,workspace_key,owner_account_id,name,workspace_type) VALUES(%s,%s,%s,'Personal','personal')",
            (ident["workspace"], f"personal:{ident['account']}", ident["account"]),
        )
        cur.execute(
            "INSERT INTO workspace_members(workspace_id,account_id,member_role,status) VALUES(%s,%s,'owner','active')",
            (ident["workspace"], ident["account"]),
        )


def _debt(cur, user_id, workspace_id, name="Synthetic debt") -> int:
    cur.execute(
        """INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id)
           VALUES(%s,%s,'other',1000,800,100,%s) RETURNING id""",
        (user_id, name, workspace_id),
    )
    return cur.fetchone()[0]


def _payment(cur, user_id, debt_id, workspace_id) -> int:
    cur.execute(
        "INSERT INTO debt_payments(user_id,debt_id,amount,workspace_id) VALUES(%s,%s,10,%s) RETURNING id",
        (user_id, debt_id, workspace_id),
    )
    return cur.fetchone()[0]


def _add_phase_2a_fks(cur) -> None:
    for table in ("debts", "debt_payments", "transactions", "expenses", "receivables", "receivable_payments", "exchange_rates"):
        cur.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_workspace FOREIGN KEY (workspace_id) "
            "REFERENCES workspaces(id) ON DELETE CASCADE NOT VALID"
        )


@pytest.fixture
def seeded(db):
    """Every classification the migration must distinguish, with synthetic rows."""
    A, B, C = IDENTITIES["A"], IDENTITIES["B"], IDENTITIES["C"]
    rows = {}
    with db["conn"].cursor() as cur:
        rows["ok_users_space_collision"] = _debt(cur, A["users"], A["workspace"])  # DINCR writer
        rows["ok_allowed_space"] = _debt(cur, A["allowed"], A["workspace"])  # Owner-style writer
        rows["foreign_user"] = _debt(cur, A["allowed"], B["workspace"])  # user of A in workspace of B
        rows["workspace_null_debt"] = _debt(cur, A["allowed"], None)  # Phase 2A would guess from user_id
        rows["safe_child"] = _payment(cur, A["allowed"], rows["ok_allowed_space"], None)
        rows["null_child_foreign_user"] = _payment(cur, C["allowed"], rows["ok_allowed_space"], None)
        rows["child_parent_mismatch"] = _payment(cur, B["allowed"], rows["ok_allowed_space"], B["workspace"])
        cur.execute(
            "INSERT INTO transactions(user_id,transaction_date,description,amount,transaction_type,workspace_id) "
            "VALUES(%s,CURRENT_DATE,'Synthetic',1,'expense',%s) RETURNING id",
            (A["allowed"], MISSING_WS),
        )
        rows["orphan_transaction"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO expenses(user_id,category,amount,workspace_id) VALUES(999,'Otros',1,%s) RETURNING id",
            (A["workspace"],),
        )
        rows["unresolved_user"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO financial_input_events(account_id,workspace_id) VALUES(%s,%s) RETURNING id",
            (A["account"], B["workspace"]),
        )
        rows["account_workspace_mismatch"] = cur.fetchone()[0]
        _add_phase_2a_fks(cur)
    db["rows"] = rows
    return db


def _apply_migration(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))


def _table_state(conn) -> dict[str, list[tuple]]:
    state = {}
    with conn.cursor() as cur:
        for table in ("debts", "debt_payments", "transactions", "expenses", "financial_input_events"):
            cur.execute(f"SELECT * FROM {table} ORDER BY id")
            state[table] = cur.fetchall()
    return state


def _audit(conn) -> dict[tuple[str, int], tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT table_name,row_id,issue,classification FROM public.dincr_ownership_audit_rows(TRUE)")
        return {(t, r): (i, c) for t, r, i, c in cur.fetchall()}


def test_classification_matches_the_evidence(seeded):
    _apply_migration(seeded["conn"])
    rows, audit = seeded["rows"], _audit(seeded["conn"])
    assert audit[("debts", rows["ok_users_space_collision"])] == ("OK_ID_SPACE_COLLISION", "OK")
    assert audit[("debts", rows["ok_allowed_space"])] == ("OK", "OK")
    assert audit[("debts", rows["foreign_user"])] == ("USER_ID_FOREIGN", "NEEDS_REVIEW")
    assert audit[("debts", rows["workspace_null_debt"])] == ("WORKSPACE_NULL", "NEEDS_REVIEW")
    assert audit[("debt_payments", rows["null_child_foreign_user"])] == ("WORKSPACE_NULL", "NEEDS_REVIEW")
    assert audit[("debt_payments", rows["child_parent_mismatch"])] == ("PARENT_WORKSPACE_MISMATCH", "NEEDS_REVIEW")
    assert audit[("transactions", rows["orphan_transaction"])] == ("WORKSPACE_MISSING", "ORPHAN")
    assert audit[("expenses", rows["unresolved_user"])] == ("USER_ID_UNRESOLVED", "NEEDS_REVIEW")
    assert audit[("financial_input_events", rows["account_workspace_mismatch"])] == ("ACCOUNT_NOT_IN_WORKSPACE", "NEEDS_REVIEW")
    # The repaired child is now consistent with its parent.
    assert audit[("debt_payments", rows["safe_child"])] == ("OK", "OK")


def test_migration_repairs_only_safe_auto_fix_and_logs_it(seeded):
    conn, rows = seeded["conn"], seeded["rows"]
    before = _table_state(conn)
    _apply_migration(conn)
    after = _table_state(conn)

    # Only one column of one row changed: the safe child's workspace_id.
    changed = {
        (table, b[0]) for table in before for b, a in zip(before[table], after[table]) if b != a
    }
    assert changed == {("debt_payments", rows["safe_child"])}
    with conn.cursor() as cur:
        cur.execute("SELECT workspace_id::text FROM debt_payments WHERE id=%s", (rows["safe_child"],))
        assert cur.fetchone()[0] == WS_A
        cur.execute("SELECT table_name,row_id,column_name,old_value,new_value,reason FROM financial_ownership_repair_log")
        assert cur.fetchall() == [
            ("debt_payments", rows["safe_child"], "workspace_id", None, WS_A, "WORKSPACE_NULL_PARENT_RESOLVABLE")
        ]
        cur.execute("SELECT DISTINCT phase FROM financial_ownership_audit_snapshots ORDER BY phase")
        assert [r[0] for r in cur.fetchall()] == ["after", "before"]


def test_ambiguous_rows_are_never_modified(seeded):
    conn, rows = seeded["conn"], seeded["rows"]
    before = _table_state(conn)
    _apply_migration(conn)
    after = _table_state(conn)
    ambiguous = {
        "debts": {rows["foreign_user"], rows["workspace_null_debt"]},
        "debt_payments": {rows["null_child_foreign_user"], rows["child_parent_mismatch"]},
        "transactions": {rows["orphan_transaction"]},
        "expenses": {rows["unresolved_user"]},
        "financial_input_events": {rows["account_workspace_mismatch"]},
    }
    for table, ids in ambiguous.items():
        assert [r for r in before[table] if r[0] in ids] == [r for r in after[table] if r[0] in ids]
    # user_id is never rewritten, in any row.
    for table in ("debts", "debt_payments", "transactions", "expenses"):
        assert [r[1] for r in before[table]] == [r[1] for r in after[table]]


def test_migration_can_run_twice(seeded):
    conn = seeded["conn"]
    _apply_migration(conn)
    first = _table_state(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM pg_constraint WHERE conname LIKE 'ck\\_%%\\_workspace_required' OR conname LIKE 'fk\\_%%\\_parent_workspace'")
        constraints = cur.fetchone()[0]
    _apply_migration(conn)
    assert _table_state(conn) == first
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM financial_ownership_repair_log")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM pg_constraint WHERE conname LIKE 'ck\\_%%\\_workspace_required' OR conname LIKE 'fk\\_%%\\_parent_workspace'")
        assert cur.fetchone()[0] == constraints
        cur.execute("SELECT COUNT(DISTINCT run_id) FROM financial_ownership_audit_snapshots")
        assert cur.fetchone()[0] == 2


def test_migration_aborts_on_broken_identity_core(seeded):
    conn = seeded["conn"]
    with conn.cursor() as cur:
        cur.execute("UPDATE workspaces SET workspace_key='personal:somebody-else' WHERE id=%s", (WS_C,))
    with pytest.raises(psycopg2.Error, match="identity-core inconsistencies"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")  # the script opened the transaction block itself
        cur.execute("SELECT to_regclass('public.financial_ownership_repair_log')")
        assert cur.fetchone()[0] is None  # whole transaction rolled back
        cur.execute("SELECT workspace_id FROM debt_payments WHERE id=%s", (seeded["rows"]["safe_child"],))
        assert cur.fetchone()[0] is None


def test_user_id_of_a_cannot_land_in_workspace_of_b(seeded):
    conn = seeded["conn"]
    _apply_migration(conn)
    A, B = IDENTITIES["A"], IDENTITIES["B"]
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="financial ownership mismatch"):
            _debt(cur, A["allowed"], B["workspace"])
        with pytest.raises(psycopg2.errors.CheckViolation, match="financial ownership mismatch"):
            _debt(cur, 999, A["workspace"])
        # Both legacy spaces of the workspace's own identity are accepted.
        _debt(cur, A["allowed"], A["workspace"])
        _debt(cur, A["users"], A["workspace"])
        # Moving an existing row to another workspace is rejected too.
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("UPDATE debts SET workspace_id=%s WHERE id=%s", (B["workspace"], seeded["rows"]["ok_allowed_space"]))


def test_rows_under_review_stay_editable_by_their_workspace(seeded):
    conn, rows = seeded["conn"], seeded["rows"]
    _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("UPDATE debts SET remaining_amount=700 WHERE id=%s", (rows["foreign_user"],))
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("UPDATE debts SET user_id=999 WHERE id=%s", (rows["foreign_user"],))


def test_new_rows_require_a_workspace(seeded):
    _apply_migration(seeded["conn"])
    with seeded["conn"].cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="workspace_required"):
            _debt(cur, IDENTITIES["A"]["allowed"], None)


def test_debt_payment_keeps_the_debt_ownership(seeded):
    conn, rows = seeded["conn"], seeded["rows"]
    _apply_migration(conn)
    A, B = IDENTITIES["A"], IDENTITIES["B"]
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            _payment(cur, B["allowed"], rows["ok_allowed_space"], B["workspace"])
        _payment(cur, A["users"], rows["ok_allowed_space"], A["workspace"])
        # A cascade that would cross owners (the seeded mismatched payment lives in
        # B's workspace) fails closed instead of deleting B's row.
        with pytest.raises(psycopg2.errors.CheckViolation, match="spans 2 live owners"):
            cur.execute("DELETE FROM debts WHERE id=%s", (rows["ok_allowed_space"],))
        # A debt whose payments all share its owner still cascades.
        debt = _debt(cur, A["allowed"], A["workspace"])
        _payment(cur, A["allowed"], debt, A["workspace"])
        cur.execute("DELETE FROM debts WHERE id=%s", (debt,))
        cur.execute("SELECT COUNT(*) FROM debt_payments WHERE debt_id=%s", (debt,))
        assert cur.fetchone()[0] == 0


def test_integrity_check_is_read_only_and_fails_on_findings(seeded):
    from backend.scripts import financial_ownership_integrity_check as check

    conn = psycopg2.connect(seeded["uri"])
    before = _table_state(seeded["conn"])
    try:
        summary, present = check.collect_summary(conn)
    finally:
        conn.close()
    assert _table_state(seeded["conn"]) == before
    with seeded["conn"].cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM pg_proc WHERE proname LIKE 'dincr\\_%%'")
        assert cur.fetchone()[0] == 0  # nothing persisted; migration not applied
    results = {r["table"]: r for r in check.evaluate(summary, present)}
    assert results["debts"]["status"] == "FAIL"
    assert results["debt_payments"]["issues"][("SAFE_AUTO_FIX", "WORKSPACE_NULL_PARENT_RESOLVABLE")] == 1
    assert results["receivables"]["status"] == "PASS" and results["receivables"]["rows"] == 0
    assert results["_identity"]["status"] == "PASS"
    text = "\n".join(check.render(list(results.values())))
    for secret in ("example.test", WS_A, ACC_A, "Synthetic"):
        assert secret not in text


def test_integrity_check_passes_on_clean_data(db):
    from backend.scripts import financial_ownership_integrity_check as check

    A = IDENTITIES["A"]
    with db["conn"].cursor() as cur:
        debt = _debt(cur, A["users"], A["workspace"])
        _payment(cur, A["allowed"], debt, A["workspace"])
    _apply_migration(db["conn"])
    conn = psycopg2.connect(db["uri"])
    try:
        results = check.evaluate(*check.collect_summary(conn))
    finally:
        conn.close()
    assert {r["status"] for r in results} == {"PASS"}


# --- Service layer: the real DINCR writers under the new guards -------------

def _context(ident: dict) -> dict:
    return {
        "id": ident["allowed"], "email": ident["email"], "role": "user", "status": "active",
        "account_id": ident["account"], "account_role": "user",
        "workspace_id": ident["workspace"], "workspace_role": "owner",
    }


@pytest.fixture
def service_db(db, monkeypatch):
    from backend.core import database

    _apply_migration(db["conn"])
    # The web app identifies itself as 'dincr-backend' (backend/main.py).
    monkeypatch.setattr(database, "DATABASE_URL", db["uri"])
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
    return db


def _as(ident: dict, fn, *args):
    from backend.auth.current_user import reset_current_user, set_current_user

    token = set_current_user(_context(ident))
    try:
        return fn(*args)
    finally:
        reset_current_user(token)


def test_dincr_writers_store_the_callers_workspace_and_pass_the_guard(service_db):
    from backend.user_product import service
    from backend.user_product.models import UserDebtCreateRequest

    A = IDENTITIES["A"]
    row = _as(A, service.create_user_debt, UserDebtCreateRequest(name="Synthetic card", remaining_amount=500, monthly_payment=50))
    with service_db["conn"].cursor() as cur:
        cur.execute("SELECT user_id, workspace_id::text FROM debts WHERE id=%s", (row["id"],))
        # Legacy compatibility keeps the users.id bridge; it never becomes another identity.
        assert cur.fetchone() == (A["users"], A["workspace"])
    result = _as(A, service.pay_user_debt, row["id"], 20)
    assert result["new_remaining_amount"] == 480
    with service_db["conn"].cursor() as cur:
        cur.execute("SELECT user_id, workspace_id::text FROM transactions WHERE source='finva_debt_payment'")
        assert cur.fetchall() == [(A["users"], A["workspace"])]


def test_user_a_cannot_read_or_modify_user_b(service_db):
    from fastapi import HTTPException

    from backend.user_product import service
    from backend.user_product.models import UserDebtCreateRequest, UserDebtUpdateRequest

    A, B = IDENTITIES["A"], IDENTITIES["B"]
    debt_b = _as(B, service.create_user_debt, UserDebtCreateRequest(name="Synthetic loan", remaining_amount=900))
    assert all(d["id"] != debt_b["id"] for d in _as(A, service.list_user_debts))
    for attempt in (
        lambda: service.pay_user_debt(debt_b["id"], 100),
        lambda: service.update_user_debt(debt_b["id"], UserDebtUpdateRequest(name="x", remaining_amount=1)),
        lambda: service.delete_user_debt(debt_b["id"]),
    ):
        with pytest.raises(HTTPException) as exc:
            _as(A, attempt)
        assert exc.value.status_code == 404
    with service_db["conn"].cursor() as cur:
        cur.execute("SELECT remaining_amount, name, workspace_id::text FROM debts WHERE id=%s", (debt_b["id"],))
        remaining, name, workspace = cur.fetchone()
    assert (float(remaining), name, workspace) == (900.0, "Synthetic loan", B["workspace"])


def test_an_ownership_table_without_id_is_reported_not_skipped(db):
    with db["conn"].cursor() as cur:
        cur.execute("CREATE TABLE savings (user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID)")
    _apply_migration(db["conn"])
    audit = _audit(db["conn"])
    assert audit[("savings", None)] == ("TABLE_NOT_AUDITABLE", "NEEDS_REVIEW")


# --- Colliding id layout -------------------------------------------------------
# (allowed_users.id, users.id) per synthetic account. a3 writes users.id 21, which
# is also a1's allowed_users.id; a6 writes users.id 24, also a2's
# allowed_users.id; a5 has no users row yet; the owner has the same id in both
# spaces. Arbitrary numbers with the collision shapes the audit must handle.
LAYOUT = {"owner": (3, 3), "a1": (21, 15), "a2": (24, 12), "a3": (26, 21), "a4": (28, 18), "a5": (31, None), "a6": (35, 24)}
A3_USERS, A2_USERS, OWNER_ID = 21, 12, 3


def _ids(label: str) -> dict:
    allowed, users = LAYOUT[label]
    account = str(uuid.uuid5(uuid.NAMESPACE_URL, f"account:{label}"))
    return {"label": label, "allowed": allowed, "users": users, "account": account,
            "workspace": str(uuid.uuid5(uuid.NAMESPACE_URL, f"workspace:{label}")),
            "email": f"{label}@example.test", "role": "owner" if label == "owner" else "user"}


def _seed_layout(cur) -> None:
    for label in LAYOUT:
        ident = _ids(label)
        cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,%s,'active')",
                    (ident["allowed"], ident["email"], ident["role"]))
        if ident["users"] is not None:
            cur.execute("INSERT INTO users(id,email,name,country,timezone) VALUES(%s,%s,'Synthetic','Nowhere','UTC')",
                        (ident["users"], ident["email"]))
        cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email,role) VALUES(%s,%s,%s,%s)",
                    (ident["account"], ident["allowed"], ident["email"], ident["role"]))
        cur.execute("INSERT INTO workspaces(id,workspace_key,owner_account_id,name,workspace_type) VALUES(%s,%s,%s,'Personal','personal')",
                    (ident["workspace"], f"personal:{ident['account']}", ident["account"]))
        cur.execute("INSERT INTO workspace_members(workspace_id,account_id,member_role,status) VALUES(%s,%s,'owner','active')",
                    (ident["workspace"], ident["account"]))
    cur.execute("SELECT setval('allowed_users_id_seq', (SELECT MAX(id) FROM allowed_users))")
    cur.execute("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))")


@pytest.fixture
def layout(admin_uri):
    uri, conn, drop = _create_database(admin_uri, _seed_layout)
    try:
        with conn.cursor() as cur:
            # Historical rows as the legacy writers store them.
            ids = {
                "a3_debt": _debt(cur, A3_USERS, _ids("a3")["workspace"]),     # users.id of a3 == allowed id of a1
                "a2_debt": _debt(cur, A2_USERS, _ids("a2")["workspace"]),     # users.id of a2, no collision
                "owner_debt": _debt(cur, OWNER_ID, _ids("owner")["workspace"]),
            }
            _add_phase_2a_fks(cur)
        _apply_migration(conn)
        yield {"uri": uri, "conn": conn, "rows": ids}
    finally:
        drop()


def test_id_space_collisions_stay_valid_and_are_never_rewritten(layout):
    audit = _audit(layout["conn"])
    assert audit[("debts", layout["rows"]["a3_debt"])] == ("OK_ID_SPACE_COLLISION", "OK")
    assert audit[("debts", layout["rows"]["a2_debt"])] == ("OK", "OK")
    assert audit[("debts", layout["rows"]["owner_debt"])] == ("OK", "OK")
    with layout["conn"].cursor() as cur:
        cur.execute("SELECT id, user_id FROM debts ORDER BY id")
        assert cur.fetchall() == [(layout["rows"]["a3_debt"], A3_USERS), (layout["rows"]["a2_debt"], A2_USERS),
                                  (layout["rows"]["owner_debt"], OWNER_ID)]
        cur.execute("SELECT COUNT(*) FROM financial_ownership_repair_log")
        assert cur.fetchone()[0] == 0


def test_cross_workspace_writes_are_rejected_with_colliding_ids(layout):
    with layout["conn"].cursor() as cur:
        for user_id, label in ((21, "a6"), (24, "a3"), (18, "a3"), (28, "a2"), (3, "a4"), (31, "owner")):
            with pytest.raises(psycopg2.errors.CheckViolation):
                _debt(cur, user_id, _ids(label)["workspace"])
        # The DINCR bridge id of each person is accepted in their own workspace.
        for label in ("a1", "a2", "a3", "a4", "a6"):
            _debt(cur, _ids(label)["users"], _ids(label)["workspace"])
        # A bare integer cannot say which space it came from: 21 IS an identity of a1.
        # This is why no reader may ever decide ownership by user_id (static guard).
        _debt(cur, A3_USERS, _ids("a1")["workspace"])


def test_account_without_users_row_writes_through_both_paths(layout, monkeypatch):
    from backend.core import database
    from backend.user_product import service
    from backend.user_product.models import UserDebtCreateRequest

    a5 = _ids("a5")
    with layout["conn"].cursor() as cur:
        _debt(cur, a5["allowed"], a5["workspace"])  # allowed_users-space writer (e.g. overtime)
    monkeypatch.setattr(database, "DATABASE_URL", layout["uri"])
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
    row = _as(a5, service.create_user_debt, UserDebtCreateRequest(name="Synthetic", remaining_amount=10))
    with layout["conn"].cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email=%s", (a5["email"],))
        created_users_id = cur.fetchone()[0]
        cur.execute("SELECT user_id FROM debts WHERE id=%s", (row["id"],))
        assert cur.fetchone()[0] == created_users_id  # lazily created bridge row, never another person's id
    assert created_users_id not in {users for _, users in LAYOUT.values() if users}


def test_owner_and_active_member_can_write_disabled_member_cannot(layout):
    a4, a5 = _ids("a4"), _ids("a5")
    with layout["conn"].cursor() as cur:
        _debt(cur, OWNER_ID, _ids("owner")["workspace"])
        cur.execute("INSERT INTO workspace_members(workspace_id,account_id,member_role,status) VALUES(%s,%s,'member','active')",
                    (a4["workspace"], a5["account"]))
        _debt(cur, a5["allowed"], a4["workspace"])
        cur.execute("UPDATE workspace_members SET status='disabled' WHERE workspace_id=%s AND account_id=%s",
                    (a4["workspace"], a5["account"]))
        with pytest.raises(psycopg2.errors.CheckViolation):
            _debt(cur, a5["allowed"], a4["workspace"])


def test_canonical_writer_without_legacy_id_and_owner_default_fallback(layout):
    a3 = _ids("a3")
    with layout["conn"].cursor() as cur:
        # DEFAULT 1 (the Owner) must never land in a user's workspace silently.
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO debts(name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id) "
                        "VALUES('x','other',1,1,0,%s)", (a3["workspace"],))
        # Future phase: the legacy column becomes optional; ownership stays workspace_id.
        cur.execute("ALTER TABLE debts ALTER COLUMN user_id DROP NOT NULL, ALTER COLUMN user_id DROP DEFAULT")
        canonical = _debt(cur, None, a3["workspace"])
    assert _audit(layout["conn"])[("debts", canonical)] == ("OK_NO_LEGACY_ID", "OK")


def test_account_deletion_still_cascades_with_the_guards(layout):
    a3 = _ids("a3")
    with layout["conn"].cursor() as cur:
        _payment(cur, A3_USERS, layout["rows"]["a3_debt"], a3["workspace"])
        cur.execute("DELETE FROM accounts WHERE id=%s", (a3["account"],))
        cur.execute("SELECT COUNT(*) FROM debts WHERE workspace_id=%s", (a3["workspace"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM debt_payments WHERE workspace_id=%s", (a3["workspace"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM debts")
        assert cur.fetchone()[0] == 2  # nobody else's rows were touched


ROLLBACK = ROOT / "database/rollback/20260925140000_financial_ownership_integrity_rollback.sql"


def test_rollback_removes_guards_keeps_evidence_and_can_revert_a_run(seeded):
    conn, rows = seeded["conn"], seeded["rows"]
    _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT run_id FROM financial_ownership_repair_log")
        run_id = cur.fetchone()[0]
    rollback = ROLLBACK.read_text(encoding="utf-8")
    step2 = rollback[rollback.index("-- DO $$"):rollback.index("COMMIT;")]
    enabled = "\n".join(line[3:] for line in step2.splitlines()).replace("<RUN_ID>", str(run_id))
    with conn.cursor() as cur:
        cur.execute(rollback.replace("COMMIT;", enabled + "\nCOMMIT;"))
        cur.execute("SELECT workspace_id FROM debt_payments WHERE id=%s", (rows["safe_child"],))
        assert cur.fetchone()[0] is None  # repair reverted
        cur.execute("SELECT COUNT(*) FROM financial_ownership_repair_log")
        assert cur.fetchone()[0] == 1  # evidence kept
        _debt(cur, IDENTITIES["A"]["allowed"], IDENTITIES["B"]["workspace"])  # guards gone
        cur.execute("SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'trg\\_%%\\_ownership_guard' OR tgname LIKE 'trg\\_%%\\_delete_guard' OR tgname LIKE 'trg\\_%%\\_truncate_guard'")
        assert cur.fetchone()[0] == 0
        cur.execute(rollback)  # a second rollback run finds nothing to remove and succeeds
    _apply_migration(conn)  # re-applying after a rollback works


@pytest.fixture
def layout_unmigrated(admin_uri):
    uri, conn, drop = _create_database(admin_uri, _seed_layout)
    try:
        with conn.cursor() as cur:
            _add_phase_2a_fks(cur)
        yield {"uri": uri, "conn": conn}
    finally:
        drop()


def test_child_with_a_colliding_id_is_never_auto_repaired(layout_unmigrated):
    """A3_USERS is a1's allowed_users.id AND a3's users.id: it cannot prove the owner."""
    conn, a1 = layout_unmigrated["conn"], _ids("a1")
    with conn.cursor() as cur:
        debt = _debt(cur, a1["allowed"], a1["workspace"])
        colliding = _payment(cur, A3_USERS, debt, None)
        unambiguous = _payment(cur, a1["users"], debt, None)
    _apply_migration(conn)
    audit = _audit(conn)
    assert audit[("debt_payments", colliding)] == ("WORKSPACE_NULL", "NEEDS_REVIEW")
    with conn.cursor() as cur:
        cur.execute("SELECT id, workspace_id::text FROM debt_payments ORDER BY id")
        assert cur.fetchall() == [(colliding, None), (unambiguous, a1["workspace"])]


def test_existing_rows_cannot_be_moved_between_workspaces(layout):
    with layout["conn"].cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="ownership change"):
            cur.execute("UPDATE debts SET workspace_id=%s WHERE id=%s", (_ids("a1")["workspace"], layout["rows"]["a3_debt"]))


def test_upsert_keeps_a_row_under_review_editable(layout_unmigrated):
    """transactions/service.py rewrites workspace_id in its ON CONFLICT clause."""
    conn, a3 = layout_unmigrated["conn"], _ids("a3")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO exchange_rates(user_id,workspace_id,rate_date,currency,exchange_rate) "
                    "VALUES(999,%s,'2026-01-02','USD',500)", (a3["workspace"],))  # NEEDS_REVIEW row
    _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO exchange_rates (user_id, workspace_id, rate_date, currency, exchange_rate, source)
               VALUES (%s, %s, %s::date, UPPER(%s), %s, %s)
               ON CONFLICT (workspace_id, rate_date, currency)
               DO UPDATE SET workspace_id = EXCLUDED.workspace_id,
                             exchange_rate = EXCLUDED.exchange_rate,
                             source = EXCLUDED.source,
                             updated_at = NOW()""",
            (a3["allowed"], a3["workspace"], "2026-01-02", "usd", 510, "manual"),
        )
        cur.execute("SELECT user_id, exchange_rate FROM exchange_rates")
        assert [(r[0], float(r[1])) for r in cur.fetchall()] == [(999, 510.0)]


def test_migration_aborts_when_a_mail_connection_id_is_outside_its_workspace(layout_unmigrated):
    conn, a3 = layout_unmigrated["conn"], _ids("a3")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id) VALUES(%s,%s,%s)",
                    (a3["account"], a3["workspace"], A2_USERS))
    with pytest.raises(psycopg2.Error, match="stored legacy ids outside their workspace"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")
        cur.execute("UPDATE finva_gmail_connections SET legacy_user_id=%s", (A3_USERS,))
    _apply_migration(conn)


def test_email_bridge_ignores_case_and_surrounding_spaces(layout):
    a3 = _ids("a3")
    with layout["conn"].cursor() as cur:
        cur.execute("UPDATE accounts SET primary_email=%s WHERE id=%s", (f"  {a3['email'].upper()} ", a3["account"]))
        _debt(cur, A3_USERS, a3["workspace"])


def test_application_writes_cannot_fill_a_null_workspace(seeded):
    _apply_migration(seeded["conn"])
    with seeded["conn"].cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="ownership change"):
            cur.execute("UPDATE debts SET workspace_id=%s WHERE id=%s", (WS_A, seeded["rows"]["workspace_null_debt"]))


def test_rerun_repairs_a_child_once_a_human_resolved_its_parent(seeded):
    conn, rows = seeded["conn"], seeded["rows"]
    with conn.cursor() as cur:
        orphan_child = _payment(cur, IDENTITIES["A"]["allowed"], rows["workspace_null_debt"], None)
    _apply_migration(conn)
    with conn.cursor() as cur:
        # The documented review procedure: one transaction, guard disabled.
        cur.execute("BEGIN")
        cur.execute("ALTER TABLE debts DISABLE TRIGGER trg_debts_ownership_guard")
        cur.execute("UPDATE debts SET workspace_id=%s WHERE id=%s", (WS_A, rows["workspace_null_debt"]))
        cur.execute("ALTER TABLE debts ENABLE TRIGGER trg_debts_ownership_guard")
        cur.execute("COMMIT")
    _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT workspace_id::text FROM debt_payments WHERE id=%s", (orphan_child,))
        assert cur.fetchone()[0] == WS_A
        cur.execute("SELECT COUNT(*) FROM pg_trigger WHERE tgname='trg_debt_payments_ownership_guard' AND tgenabled='O'")
        assert cur.fetchone()[0] == 1  # guard re-enabled after the repair


def test_user_id_fk_rules_are_reported(db):
    with db["conn"].cursor() as cur:
        cur.execute("ALTER TABLE debts ADD CONSTRAINT debts_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE NOT VALID")
        cur.execute("ALTER TABLE expenses ADD CONSTRAINT expenses_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT NOT VALID")
    _apply_migration(db["conn"])
    audit = _audit(db["conn"])
    assert audit[("debts", None)] == ("USER_ID_FK_TO_USERS_ON_DELETE_CASCADE", "INFO")
    assert audit[("expenses", None)] == ("USER_ID_FK_TO_USERS_ON_DELETE_RESTRICT", "INFO")


# --- The FK decides the id space (production: debts.user_id -> users ON DELETE CASCADE,
# fixed_expenses-style tables -> allowed_users) ------------------------------------

@pytest.fixture
def layout_fk(layout_unmigrated):
    """Colliding ids plus both FK shapes: debts/transactions -> users (as in production)
    and a synthetic allowed_users FK on expenses (production: fixed_expenses-style tables)."""
    conn = layout_unmigrated["conn"]
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE debts ADD CONSTRAINT debts_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE")
        cur.execute("ALTER TABLE transactions ADD CONSTRAINT transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE")
        cur.execute("ALTER TABLE expenses ADD CONSTRAINT expenses_user_id_fkey FOREIGN KEY (user_id) REFERENCES allowed_users(id) ON DELETE CASCADE")
    return layout_unmigrated


def _legacy_row(conn, fn, *args):
    """Insert a row the way old writers could, bypassing the guard (legacy data)."""
    with conn.cursor() as cur:
        cur.execute("BEGIN")
        cur.execute("ALTER TABLE transactions DISABLE TRIGGER trg_transactions_ownership_guard")
        row = fn(cur, *args)
        cur.execute("ALTER TABLE transactions ENABLE TRIGGER trg_transactions_ownership_guard")
        cur.execute("COMMIT")
    return row


def _transaction(cur, user_id, workspace_id) -> int:
    cur.execute("INSERT INTO transactions(user_id,transaction_date,description,amount,transaction_type,workspace_id) "
                "VALUES(%s,CURRENT_DATE,'Synthetic',1,'expense',%s) RETURNING id", (user_id, workspace_id))
    return cur.fetchone()[0]


def test_wrong_space_row_is_deleted_by_an_unrelated_persons_cascade(layout_fk):
    """The hazard itself, without the migration: a2 writes its allowed_users.id (24)
    into a users-FK table; 24 is a6's users.id, so deleting a6 deletes a2's row."""
    conn, a2, a6 = layout_fk["conn"], _ids("a2"), _ids("a6")
    with conn.cursor() as cur:
        victim = _transaction(cur, a2["allowed"], a2["workspace"])
        cur.execute("DELETE FROM users WHERE id=%s", (a6["users"],))
        cur.execute("SELECT COUNT(*) FROM transactions WHERE id=%s", (victim,))
        assert cur.fetchone()[0] == 0


def test_existing_wrong_space_rows_are_flagged_and_left_untouched(layout_fk):
    conn, a2, a3 = layout_fk["conn"], _ids("a2"), _ids("a3")
    with conn.cursor() as cur:
        right = _debt(cur, a3["users"], a3["workspace"])            # users-space, collides with a1's allowed id
    _apply_migration(conn)
    wrong = _legacy_row(conn, _transaction, a2["allowed"], a2["workspace"])  # a2's allowed id in a users-FK table
    audit = _audit(conn)
    assert audit[("transactions", wrong)] == ("USER_ID_WRONG_SPACE", "NEEDS_REVIEW")
    assert audit[("debts", right)] == ("OK", "OK")  # the FK removes the ambiguity: no collision here
    with conn.cursor() as cur:
        cur.execute("SELECT user_id, workspace_id::text FROM transactions WHERE id=%s", (wrong,))
        assert cur.fetchone() == (a2["allowed"], a2["workspace"])


def test_guard_enforces_the_fk_space_for_new_writes(layout_fk):
    conn = layout_fk["conn"]
    _apply_migration(conn)
    a1, a2, a3 = _ids("a1"), _ids("a2"), _ids("a3")
    with conn.cursor() as cur:
        # users-FK table: only the workspace's users.id.
        _debt(cur, a3["users"], a3["workspace"])
        with pytest.raises(psycopg2.errors.CheckViolation):
            _transaction(cur, a2["allowed"], a2["workspace"])     # would attach the row to a6
        with pytest.raises(psycopg2.errors.CheckViolation):
            _debt(cur, a1["allowed"], a1["workspace"])            # 21 is a3's users row, not a1's
        # allowed_users-FK table: only the workspace's allowed_users.id.
        cur.execute("INSERT INTO expenses(user_id,category,amount,workspace_id) VALUES(%s,'Otros',1,%s)", (a1["allowed"], a1["workspace"]))
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO expenses(user_id,category,amount,workspace_id) VALUES(%s,'Otros',1,%s)", (a1["users"], a1["workspace"]))
        # The owner's ids coincide in both spaces and work everywhere.
        _debt(cur, OWNER_ID, _ids("owner")["workspace"])


def test_dincr_writers_pass_the_fk_space_guard(layout_fk, monkeypatch):
    from backend.core import database
    from backend.user_product import service
    from backend.user_product.models import UserDebtCreateRequest

    _apply_migration(layout_fk["conn"])
    monkeypatch.setattr(database, "DATABASE_URL", layout_fk["uri"])
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
    a3 = _ids("a3")
    row = _as(a3, service.create_user_debt, UserDebtCreateRequest(name="Synthetic", remaining_amount=100))
    result = _as(a3, service.pay_user_debt, row["id"], 10)  # writes a transaction (users-FK) too
    assert result["new_remaining_amount"] == 90


def test_migration_aborts_when_an_owner_ids_differ_across_spaces(layout_fk):
    conn, owner = layout_fk["conn"], _ids("owner")
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET email='someone-else@example.test' WHERE id=%s", (owner["users"],))
    with pytest.raises(psycopg2.Error, match="owner/admin accounts"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")


def test_migration_aborts_when_overtime_table_references_users(layout_unmigrated):
    conn = layout_unmigrated["conn"]
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE payroll_events (id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL "
                    "REFERENCES users(id) ON DELETE CASCADE, workspace_id UUID)")
    with pytest.raises(psycopg2.Error, match="payroll_events.user_id references users"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")


# --- Deletions: a cleanup that selects rows by a legacy user_id from the wrong
# id space deletes other people's rows --------------------------------------------

INCIDENT_SCRIPT = """
DO $$
DECLARE
    target_workspaces uuid[] := ARRAY['%(ws)s'::uuid];
    target_legacy bigint[] := ARRAY[%(legacy)s];
BEGIN
    EXECUTE 'DELETE FROM public.debts WHERE workspace_id = ANY($1) OR user_id = ANY($2)'
        USING target_workspaces, target_legacy;
END $$;
"""


def _incident(cur, target: dict) -> None:
    # The script's author meant the target's allowed_users.id; in a users-FK table
    # the same integer is another person's users.id.
    cur.execute(INCIDENT_SCRIPT % {"ws": target["workspace"], "legacy": target["allowed"]})


def test_incident_script_deletes_another_tenants_debts_without_the_guard(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    with conn.cursor() as cur:
        victim = _debt(cur, a3["users"], a3["workspace"])     # users.id 21 == a1's allowed_users.id
        _debt(cur, a1["users"], a1["workspace"])              # the target's own debt
        _incident(cur, a1)
        cur.execute("SELECT COUNT(*) FROM debts WHERE id=%s", (victim,))
        assert cur.fetchone()[0] == 0  # the victim's debt is gone


def test_delete_guard_rejects_the_incident_script(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    with conn.cursor() as cur:
        victim = _debt(cur, a3["users"], a3["workspace"])
        _debt(cur, a1["users"], a1["workspace"])
    _apply_migration(conn)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="spans 2 live owners"):
            _incident(cur, a1)
        cur.execute("SELECT COUNT(*) FROM debts WHERE id=%s", (victim,))
        assert cur.fetchone()[0] == 1
        # Deleting only the target's rows, by workspace, is allowed and logged.
        cur.execute("DELETE FROM debts WHERE workspace_id=%s", (a1["workspace"],))
        cur.execute("SELECT table_name, row_count, workspace_ids::text[] FROM financial_ownership_delete_log")
        assert cur.fetchall() == [("debts", 1, [a1["workspace"]])]


def test_app_deletes_and_cascades_still_work_and_are_logged(layout_fk):
    conn, a3 = layout_fk["conn"], _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        debt = _debt(cur, a3["users"], a3["workspace"])
        _payment(cur, a3["users"], debt, a3["workspace"])
        cur.execute("DELETE FROM debts WHERE id=%s AND workspace_id=%s", (debt, a3["workspace"]))
        cur.execute("SELECT table_name, row_count FROM financial_ownership_delete_log ORDER BY id")
        logged = cur.fetchall()
    assert ("debts", 1) in logged and ("debt_payments", 1) in logged


def test_account_deletion_cascade_is_not_blocked(layout_fk):
    conn, a3 = layout_fk["conn"], _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        _debt(cur, a3["users"], a3["workspace"])
        cur.execute("DELETE FROM accounts WHERE id=%s", (a3["account"],))       # workspace cascade
        cur.execute("DELETE FROM users WHERE lower(email)=lower(%s)", (a3["email"],))
        cur.execute("DELETE FROM allowed_users WHERE id=%s", (a3["allowed"],))
        cur.execute("SELECT COUNT(*) FROM debts WHERE workspace_id=%s", (a3["workspace"],))
        assert cur.fetchone()[0] == 0


def test_identity_delete_cannot_cascade_into_another_workspace(layout_fk):
    conn, a2, a6 = layout_fk["conn"], _ids("a2"), _ids("a6")
    _apply_migration(conn)
    wrong = _legacy_row(conn, _transaction, a2["allowed"], a2["workspace"])  # 24 is a6's users.id
    with conn.cursor() as cur:
        cur.execute("DELETE FROM accounts WHERE id=%s", (a6["account"],))  # the app's order: account first
        with pytest.raises(psycopg2.errors.ForeignKeyViolation, match="another workspace"):
            cur.execute("DELETE FROM users WHERE id=%s", (a6["users"],))
        cur.execute("SELECT COUNT(*) FROM transactions WHERE id=%s", (wrong,))
        assert cur.fetchone()[0] == 1


def test_truncate_of_a_financial_table_is_rejected(layout_fk):
    conn = layout_fk["conn"]
    _apply_migration(conn)
    with conn.cursor() as cur:
        _debt(cur, _ids("a3")["users"], _ids("a3")["workspace"])
        with pytest.raises(psycopg2.errors.CheckViolation, match="TRUNCATE of financial table"):
            cur.execute("TRUNCATE debts CASCADE")
        cur.execute("SELECT COUNT(*) FROM debts")
        assert cur.fetchone()[0] == 1


def test_manual_session_must_declare_the_workspace_it_deletes_from(layout_fk):
    """The single-owner shape: only the victim has matching rows."""
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    with conn.cursor() as cur:
        victim = _debt(cur, a3["users"], a3["workspace"])
    _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("BEGIN")
        cur.execute("SET LOCAL application_name = 'supabase/dashboard-query-editor'")
        with pytest.raises(psycopg2.errors.CheckViolation, match="outside the declared workspace"):
            _incident(cur, a1)            # target a1 has no debts: every match is the victim's
        cur.execute("ROLLBACK")
        cur.execute("BEGIN")
        cur.execute("SET LOCAL application_name = 'supabase/dashboard-query-editor'")
        cur.execute("SELECT set_config('dincr.delete_workspace', %s, true)", (a1["workspace"],))
        with pytest.raises(psycopg2.errors.CheckViolation, match="outside the declared workspace"):
            _incident(cur, a1)            # declared a1, but the rows belong to a3
        cur.execute("ROLLBACK")
        cur.execute("BEGIN")
        cur.execute("SET LOCAL application_name = 'supabase/dashboard-query-editor'")
        cur.execute("SELECT set_config('dincr.delete_workspace', %s, true)", (a3["workspace"],))
        cur.execute("DELETE FROM debts WHERE id=%s AND workspace_id=%s", (victim, a3["workspace"]))
        cur.execute("COMMIT")             # an explicit, declared cleanup of one workspace works


def test_account_deletion_logs_only_a_count(layout_fk):
    conn, a3 = layout_fk["conn"], _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        _debt(cur, a3["users"], a3["workspace"])
        cur.execute("DELETE FROM accounts WHERE id=%s", (a3["account"],))
        cur.execute("SELECT row_count, row_ids, workspace_ids::text[] FROM financial_ownership_delete_log WHERE table_name='debts'")
        assert cur.fetchall() == [(1, [], [])]


def test_migration_aborts_on_wrong_space_rows(layout_fk):
    conn, a2 = layout_fk["conn"], _ids("a2")
    with conn.cursor() as cur:
        _transaction(cur, a2["allowed"], a2["workspace"])
    with pytest.raises(psycopg2.Error, match="legacy id from the wrong space"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")


def test_unknown_client_must_declare_too(layout_fk):
    """Scripts, the CLI or agents (any name but the app's) are not exempt."""
    conn, a3 = layout_fk["conn"], _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        debt = _debt(cur, a3["users"], a3["workspace"])
        cur.execute("BEGIN")
        cur.execute("SET LOCAL application_name = ''")
        with pytest.raises(psycopg2.errors.CheckViolation, match="outside the declared workspace"):
            cur.execute("DELETE FROM debts WHERE id=%s", (debt,))
        cur.execute("ROLLBACK")


def test_connection_names_web_app_vs_scripts():
    """Run in a fresh interpreter: scripts default to a non-exempt name, the web
    entrypoint labels its connections as the app."""
    import subprocess
    import sys

    code = (
        "import os; os.environ.pop('DINCR_DB_APPLICATION_NAME', None)\n"
        "from backend.core import database\n"
        "assert database.APPLICATION_NAME == 'dincr-script', database.APPLICATION_NAME\n"
        "import backend.main\n"
        "assert database.APPLICATION_NAME == 'dincr-backend', database.APPLICATION_NAME\n"
        "seen = {}\n"
        "database.DATABASE_URL = 'postgresql://example.invalid/db'\n"
        "database.psycopg2.connect = lambda *a, **k: seen.update(k) or object()\n"
        "database.PostgresConnection()\n"
        "assert seen['application_name'] == 'dincr-backend'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]


def _orphan_after_migration(conn, ids) -> int:
    """A row without a workspace can only appear if its CHECK is gone (a regression)."""
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE debts DROP CONSTRAINT ck_debts_workspace_required")
        cur.execute("ALTER TABLE debts DISABLE TRIGGER trg_debts_ownership_guard")
        orphan = _debt(cur, ids["users"], None, name="Orphan debt")
        cur.execute("ALTER TABLE debts ENABLE TRIGGER trg_debts_ownership_guard")
    return orphan


WORKSPACE_ONLY = ("finva_budget_items", "finva_recurring_items", "finva_goal_contributions",
                  "finva_savings_plans", "finva_savings_plan_contributions")


def _contribution(cur, ids) -> int:
    cur.execute("INSERT INTO finva_goal_contributions(workspace_id, goal_id, amount) VALUES (%s, 1, 10) RETURNING id",
                (ids["workspace"],))
    return cur.fetchone()[0]


def test_workspace_only_financial_tables_get_delete_and_truncate_guards(layout_fk):
    conn = layout_fk["conn"]
    _apply_migration(conn)
    with conn.cursor() as cur:
        for table in WORKSPACE_ONLY:
            cur.execute("SELECT tgname FROM pg_trigger WHERE tgrelid = %s::regclass AND NOT tgisinternal ORDER BY 1",
                        (f"public.{table}",))
            assert [row[0] for row in cur.fetchall()] == [f"trg_{table}_delete_guard", f"trg_{table}_truncate_guard",
                                                          f"trg_{table}_workspace_move_guard"]
        # No ownership trigger: these tables have no legacy user_id.
        cur.execute("SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'trg_finva_%_ownership_guard'")
        assert cur.fetchone()[0] == 0


def test_a_cross_owner_delete_of_goal_contributions_is_rejected(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        _contribution(cur, a1)
        _contribution(cur, a3)
        with pytest.raises(psycopg2.errors.CheckViolation, match="spans 2 live owners"):
            cur.execute("DELETE FROM finva_goal_contributions WHERE workspace_id = ANY(%s::uuid[])",
                        ([a1["workspace"], a3["workspace"]],))
        with pytest.raises(psycopg2.errors.CheckViolation, match="TRUNCATE of financial table"):
            cur.execute("TRUNCATE finva_goal_contributions")
        cur.execute("SELECT COUNT(*) FROM finva_goal_contributions")
        assert cur.fetchone()[0] == 2
        # The app deleting one workspace's rows still works.
        cur.execute("DELETE FROM finva_goal_contributions WHERE workspace_id = %s", (a1["workspace"],))
        cur.execute("SELECT COUNT(*) FROM finva_goal_contributions")
        assert cur.fetchone()[0] == 1


def test_migration_refuses_to_run_before_the_request_path_schema(layout_fk):
    conn = layout_fk["conn"]
    with conn.cursor() as cur:
        cur.execute("DROP TABLE finva_goal_contributions")
    with pytest.raises(psycopg2.Error, match="apply 20260925130000_request_path_schema.sql first"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")
        cur.execute("SELECT to_regprocedure('public.dincr_guard_financial_delete()') IS NULL")
        assert cur.fetchone()[0] is True  # nothing was applied


def _manual(cur, declared=None):
    cur.execute("BEGIN")
    cur.execute("SET LOCAL application_name = 'supabase/dashboard-query-editor'")
    if declared is not None:
        cur.execute("SELECT set_config('dincr.delete_workspace', %s, true)", (declared,))


def test_rows_without_a_workspace_need_an_explicit_declaration(layout_fk):
    """Orphans (owner unclear) cannot ride along with a declared workspace's cleanup."""
    conn, a1 = layout_fk["conn"], _ids("a1")
    with conn.cursor() as cur:
        own = _debt(cur, a1["users"], a1["workspace"])
    _apply_migration(conn)
    orphan = _orphan_after_migration(conn, a1)
    with conn.cursor() as cur:
        _manual(cur, a1["workspace"])
        with pytest.raises(psycopg2.errors.CheckViolation, match="without a workspace"):
            cur.execute("DELETE FROM debts WHERE workspace_id = %s OR workspace_id IS NULL", (a1["workspace"],))
        cur.execute("ROLLBACK")
        _manual(cur)
        with pytest.raises(psycopg2.errors.CheckViolation, match="without a workspace"):
            cur.execute("DELETE FROM debts WHERE id = %s", (orphan,))
        cur.execute("ROLLBACK")
        _manual(cur, "none")
        cur.execute("DELETE FROM debts WHERE id = %s AND workspace_id IS NULL", (orphan,))
        cur.execute("COMMIT")
        cur.execute("SELECT row_ids FROM financial_ownership_delete_log WHERE table_name = 'debts' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == [orphan]  # an orphan's id is kept as evidence
        cur.execute("SELECT COUNT(*) FROM debts WHERE id = %s", (own,))
        assert cur.fetchone()[0] == 1


def test_a_manual_account_deletion_must_declare_that_workspace(layout_fk):
    conn, a3 = layout_fk["conn"], _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        _debt(cur, a3["users"], a3["workspace"])
        _manual(cur)
        with pytest.raises(psycopg2.errors.CheckViolation, match="outside the declared workspace"):
            cur.execute("DELETE FROM accounts WHERE id = %s", (a3["account"],))
        cur.execute("ROLLBACK")
        _manual(cur, a3["workspace"])
        cur.execute("DELETE FROM accounts WHERE id = %s", (a3["account"],))
        cur.execute("COMMIT")
        cur.execute("SELECT COUNT(*) FROM debts WHERE workspace_id = %s", (a3["workspace"],))
        assert cur.fetchone()[0] == 0



def test_deleting_several_accounts_in_one_statement_is_rejected_for_every_session(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:  # the fixture connection is the app ('Supavisor')
        with pytest.raises(psycopg2.errors.CheckViolation, match="spans 2 accounts"):
            cur.execute("DELETE FROM accounts WHERE id = ANY(%s::uuid[])", ([a1["account"], a3["account"]],))
        cur.execute("DELETE FROM accounts WHERE id = %s", (a1["account"],))  # one account works
        cur.execute("SELECT COUNT(*) FROM accounts WHERE id = %s", (a3["account"],))
        assert cur.fetchone()[0] == 1


def test_a_users_row_cannot_go_while_its_account_lives(layout_fk):
    conn, a1 = layout_fk["conn"], _ids("a1")
    _apply_migration(conn)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.ForeignKeyViolation, match="live account"):
            cur.execute("DELETE FROM users WHERE id = %s", (a1["users"],))
        cur.execute("DELETE FROM accounts WHERE id = %s", (a1["account"],))
        cur.execute("DELETE FROM users WHERE id = %s", (a1["users"],))  # the app's order works


def test_a_table_without_an_integer_id_is_guarded_and_logged_as_a_count(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        for ids in (a1, a3):
            cur.execute("INSERT INTO financial_profiles(account_id, workspace_id, declared_income) VALUES (%s, %s, 1)",
                        (ids["account"], ids["workspace"]))
        with pytest.raises(psycopg2.errors.CheckViolation, match="spans 2 live owners"):
            cur.execute("DELETE FROM financial_profiles")
        cur.execute("DELETE FROM financial_profiles WHERE workspace_id = %s", (a1["workspace"],))
        cur.execute("SELECT row_count, row_ids FROM financial_ownership_delete_log WHERE table_name = 'financial_profiles'")
        assert cur.fetchall() == [(1, [])]


def test_migration_aborts_on_rows_pointing_at_another_accounts_identity(layout_fk):
    conn, a1, a4 = layout_fk["conn"], _ids("a1"), _ids("a4")
    with conn.cursor() as cur:
        _debt(cur, a4["users"], a1["workspace"])  # debts -> users: a4's identity in a1's workspace
    with pytest.raises(psycopg2.Error, match="reference another account's identity"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")


def test_new_guard_objects_are_closed_to_the_data_api(layout_fk):
    conn = layout_fk["conn"]
    _apply_migration(conn)
    with conn.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute("""SELECT c.relname FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace
                           AND c.relname LIKE 'financial_ownership_%%'
                           AND (has_table_privilege(%s, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')
                                OR (c.relkind = 'S' AND has_sequence_privilege(%s, c.oid, 'USAGE,SELECT,UPDATE')))""",
                        (role, role))
            assert cur.fetchall() == [], role
            cur.execute("""SELECT p.proname FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
                           AND p.proname LIKE 'dincr\\_%%' AND has_function_privilege(%s, p.oid, 'EXECUTE')""", (role,))
            assert cur.fetchall() == [], role


PREFLIGHT = ROOT / "database/audits/financial_ownership_preflight.sql"


def _preflight(conn) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(PREFLIGHT.read_text(encoding="utf-8"))
        rows = cur.fetchall()
        cur.execute("ROLLBACK")
    return rows


def test_the_preflight_reports_what_the_migration_would_abort_on(layout_fk):
    conn, a1, a4 = layout_fk["conn"], _ids("a1"), _ids("a4")
    with conn.cursor() as cur:
        _debt(cur, a4["users"], a1["workspace"])  # a4's identity in a1's workspace
        cur.execute("DROP TABLE finva_savings_plan_contributions")
    rows = _preflight(conn)
    aborts = {(r[1], r[4]) for r in rows if r[0] == "would_abort"}
    assert ("debts", "USER_ID_FOREIGN_IN_FK_TABLE") in aborts
    assert ("finva_savings_plan_contributions", "PREREQUISITE_TABLE_MISSING") in aborts
    unguarded = {r[1] for r in rows if r[0] == "unguarded_workspace_table"}
    assert "workspace_members" in unguarded and "debts" not in unguarded and "financial_profiles" not in unguarded
    with conn.cursor() as cur:  # the preflight changed nothing
        cur.execute("SELECT to_regprocedure('public.dincr_guard_financial_delete()') IS NULL")
        assert cur.fetchone()[0] is True


@pytest.mark.parametrize("with_orphan", [False, True])
def test_the_real_account_deletion_runs_under_every_guard(layout_fk, monkeypatch, with_orphan):
    """delete_current_account end to end (Supabase Auth HTTP and Vault stubbed).

    with_orphan: the person also owns a row left without a workspace (under
    review); the flow declares 'none' for its own identity cascade.
    """
    from types import SimpleNamespace

    from backend.auth import service as auth_service
    from backend.auth.current_user import reset_current_user, set_current_user
    from backend.core import database

    conn, a3, a1 = layout_fk["conn"], _ids("a3"), _ids("a1")
    auth_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "auth:a3"))
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS vault")
        cur.execute("CREATE TABLE IF NOT EXISTS vault.secrets (id UUID PRIMARY KEY, secret TEXT)")
        cur.execute("CREATE OR REPLACE VIEW vault.decrypted_secrets AS SELECT id, secret AS decrypted_secret FROM vault.secrets")
        cur.execute("ALTER TABLE finva_gmail_connections ADD COLUMN IF NOT EXISTS refresh_token_secret_id UUID, "
                    "ADD COLUMN IF NOT EXISTS granted_scopes TEXT[]")
        cur.execute("UPDATE accounts SET supabase_user_id=%s WHERE id=%s", (auth_id, a3["account"]))
        cur.execute("UPDATE allowed_users SET supabase_user_id=%s WHERE id=%s", (auth_id, a3["allowed"]))
        _debt(cur, a3["users"], a3["workspace"])
        _debt(cur, a1["users"], a1["workspace"])  # someone else's data must survive
    _apply_migration(conn)
    orphan = _orphan_after_migration(conn, a3) if with_orphan else None
    monkeypatch.setattr(database, "DATABASE_URL", layout_fk["uri"])
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
    monkeypatch.setattr(auth_service, "SUPABASE_URL", "https://auth.example.invalid")
    monkeypatch.setattr(auth_service, "SUPABASE_ADMIN_KEY", "synthetic-admin-key")
    ok = SimpleNamespace(status_code=200, ok=True, json=lambda: {}, text="")
    monkeypatch.setattr(auth_service.requests, "delete", lambda *a, **k: ok)
    monkeypatch.setattr(auth_service.requests, "get", lambda *a, **k: SimpleNamespace(status_code=404, ok=False, json=lambda: {}, text=""))
    monkeypatch.setattr(auth_service.requests, "post", lambda *a, **k: ok)

    token = set_current_user({"id": a3["allowed"], "email": a3["email"], "role": "user", "status": "active",
                              "account_id": a3["account"], "supabase_user_id": auth_id,
                              "workspace_id": a3["workspace"]})
    try:
        auth_service.delete_current_account()
    finally:
        reset_current_user(token)

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM accounts WHERE id=%s", (a3["account"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM debts WHERE workspace_id=%s", (a3["workspace"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM debts WHERE workspace_id=%s", (a1["workspace"],))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM users WHERE id=%s", (a3["users"],))
        assert cur.fetchone()[0] == 0
        if orphan:
            cur.execute("SELECT COUNT(*) FROM debts WHERE id=%s", (orphan,))
            assert cur.fetchone()[0] == 0  # the person's own orphan went with their identity


def test_a_live_accounts_allowed_users_row_cannot_be_deleted(layout_fk, monkeypatch):
    from backend.auth import service as auth_service
    from backend.core import database

    conn, a3 = layout_fk["conn"], _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.ForeignKeyViolation, match="live account"):
            cur.execute("DELETE FROM allowed_users WHERE id = %s", (a3["allowed"],))
    monkeypatch.setattr(database, "DATABASE_URL", layout_fk["uri"])
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
    assert auth_service.delete_allowed_user(a3["allowed"])["status"] == "ERROR"  # admin path refuses cleanly
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM allowed_users WHERE id = %s", (a3["allowed"],))
        assert cur.fetchone()[0] == 1


def test_a_parent_delete_spanning_owners_is_rejected_before_its_row_by_row_cascade(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:  # the app's own session
        for ids in (a1, a3):
            cur.execute("INSERT INTO finva_gmail_connections(account_id, workspace_id, legacy_user_id) VALUES (%s, %s, %s)",
                        (ids["account"], ids["workspace"], ids["allowed"]))
        with pytest.raises(psycopg2.errors.CheckViolation, match="spans 2 live owners"):
            cur.execute("DELETE FROM finva_gmail_connections")
        cur.execute("DELETE FROM finva_gmail_connections WHERE workspace_id = %s", (a1["workspace"],))


def test_rows_without_a_workspace_are_protected_in_the_apps_session_too(layout_fk):
    conn, a1 = layout_fk["conn"], _ids("a1")
    _apply_migration(conn)
    orphan = _orphan_after_migration(conn, a1)
    with conn.cursor() as cur:  # 'Supavisor', exempt from declaring workspaces
        with pytest.raises(psycopg2.errors.CheckViolation, match="without a workspace"):
            cur.execute("DELETE FROM debts WHERE id = %s", (orphan,))
        cur.execute("BEGIN")
        cur.execute("SELECT set_config('dincr.delete_workspace', 'none', true)")
        cur.execute("DELETE FROM debts WHERE id = %s", (orphan,))
        cur.execute("COMMIT")


def test_rows_of_workspace_only_tables_cannot_move_between_workspaces(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    _apply_migration(conn)
    with conn.cursor() as cur:
        row = _contribution(cur, a1)
        with pytest.raises(psycopg2.errors.CheckViolation, match="cannot move to another workspace"):
            cur.execute("UPDATE finva_goal_contributions SET workspace_id = %s WHERE id = %s", (a3["workspace"], row))
        cur.execute("UPDATE finva_goal_contributions SET workspace_id = %s, amount = 20 WHERE id = %s",
                    (a1["workspace"], row))  # same workspace (an upsert): allowed


def test_each_abort_has_its_own_sqlstate(layout_fk):
    conn = layout_fk["conn"]
    with conn.cursor() as cur:
        cur.execute("DROP TABLE finva_goal_contributions")
    with pytest.raises(psycopg2.Error) as error:
        _apply_migration(conn)
    assert error.value.pgcode == "DI007"
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")



def test_migration_aborts_on_a_profile_outside_its_personal_workspace(layout_fk):
    conn, a1, a3 = layout_fk["conn"], _ids("a1"), _ids("a3")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO financial_profiles(account_id, workspace_id) VALUES (%s, %s)", (a1["account"], a3["workspace"]))
    with pytest.raises(psycopg2.Error) as error:
        _apply_migration(conn)
    assert error.value.pgcode == "DI010"
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")


def test_new_rows_of_workspace_only_tables_need_a_workspace(layout_fk):
    conn = layout_fk["conn"]
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE finva_goal_contributions ALTER COLUMN workspace_id DROP NOT NULL")
    _apply_migration(conn)
    with conn.cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="workspace_required"):
            cur.execute("INSERT INTO finva_goal_contributions(workspace_id, goal_id, amount) VALUES (NULL, 1, 5)")


def test_the_preflight_flags_rows_without_a_workspace_that_a_colliding_id_would_misattribute(layout_fk):
    conn, a1 = layout_fk["conn"], _ids("a1")
    with conn.cursor() as cur:  # a1's allowed_users id is another person's users.id in this layout
        _debt(cur, a1["allowed"], None, name="Orphan with a colliding id")
    rows = _preflight(conn)
    assert ("debts", "ROWS_WITHOUT_WORKSPACE_WITH_COLLIDING_ID") in {(r[1], r[4]) for r in rows if r[0] == "workspace_null_collision"}


def test_the_collision_gate_ignores_an_orphan_whose_id_is_the_same_person_in_both_spaces(layout_fk):
    conn, owner = layout_fk["conn"], _ids("owner")
    with conn.cursor() as cur:  # the owner's allowed_users id equals its own users.id (same email)
        _debt(cur, owner["users"], None, name="Orphan, same person in both spaces")
    rows = _preflight(conn)
    assert not [r for r in rows if r[0] == "workspace_null_collision"]
    assert ("debts", "ROWS_WITHOUT_WORKSPACE") in {(r[1], r[4]) for r in rows if r[0] == "rows_without_workspace"}


def test_the_collision_gate_covers_guarded_tables_outside_the_ownership_list(layout_fk):
    conn, a1 = layout_fk["conn"], _ids("a1")
    with conn.cursor() as cur:  # financial_input_events: user_id -> allowed_users, not an ownership table
        cur.execute("ALTER TABLE financial_input_events ALTER COLUMN workspace_id DROP NOT NULL, "
                    "ADD COLUMN user_id BIGINT REFERENCES allowed_users(id) ON DELETE CASCADE")
        cur.execute("INSERT INTO financial_input_events(account_id, workspace_id, user_id) VALUES (%s, NULL, %s)",
                    (a1["account"], a1["allowed"]))  # a1's allowed_users id is another person's users.id here
    rows = _preflight(conn)
    assert ("financial_input_events", "ROWS_WITHOUT_WORKSPACE_WITH_COLLIDING_ID") in {
        (r[1], r[4]) for r in rows if r[0] == "workspace_null_collision"}
