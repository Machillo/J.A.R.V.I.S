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
MIGRATION = ROOT / "database/migrations/20260925120000_financial_ownership_integrity.sql"

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
    conn = psycopg2.connect(uri)
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
        # Deleting the debt still cascades to its payments.
        cur.execute("DELETE FROM debts WHERE id=%s", (rows["ok_allowed_space"],))
        cur.execute("SELECT COUNT(*) FROM debt_payments WHERE debt_id=%s", (rows["ok_allowed_space"],))
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
    monkeypatch.setattr(database, "DATABASE_URL", db["uri"])
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
# (allowed_users.id, users.id) per synthetic account. "k" writes users.id 21, which
# is also "p"'s allowed_users.id; "m" writes users.id 24, also "t"'s
# allowed_users.id; "s" has no users row yet; the owner has the same id in both
# spaces. Arbitrary numbers with the collision shapes the audit must handle.
LAYOUT = {"owner": (3, 3), "p": (21, 15), "t": (24, 12), "k": (26, 21), "e": (28, 18), "s": (31, None), "m": (35, 24)}
K_USERS, T_USERS, OWNER_ID = 21, 12, 3


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
                "k_debt": _debt(cur, K_USERS, _ids("k")["workspace"]),     # users.id of k == allowed id of p
                "t_debt": _debt(cur, T_USERS, _ids("t")["workspace"]),     # users.id of t, no collision
                "owner_debt": _debt(cur, OWNER_ID, _ids("owner")["workspace"]),
            }
            _add_phase_2a_fks(cur)
        _apply_migration(conn)
        yield {"uri": uri, "conn": conn, "rows": ids}
    finally:
        drop()


def test_id_space_collisions_stay_valid_and_are_never_rewritten(layout):
    audit = _audit(layout["conn"])
    assert audit[("debts", layout["rows"]["k_debt"])] == ("OK_ID_SPACE_COLLISION", "OK")
    assert audit[("debts", layout["rows"]["t_debt"])] == ("OK", "OK")
    assert audit[("debts", layout["rows"]["owner_debt"])] == ("OK", "OK")
    with layout["conn"].cursor() as cur:
        cur.execute("SELECT id, user_id FROM debts ORDER BY id")
        assert cur.fetchall() == [(layout["rows"]["k_debt"], K_USERS), (layout["rows"]["t_debt"], T_USERS),
                                  (layout["rows"]["owner_debt"], OWNER_ID)]
        cur.execute("SELECT COUNT(*) FROM financial_ownership_repair_log")
        assert cur.fetchone()[0] == 0


def test_cross_workspace_writes_are_rejected_with_colliding_ids(layout):
    with layout["conn"].cursor() as cur:
        for user_id, label in ((21, "m"), (24, "k"), (18, "k"), (28, "t"), (3, "e"), (31, "owner")):
            with pytest.raises(psycopg2.errors.CheckViolation):
                _debt(cur, user_id, _ids(label)["workspace"])
        # The DINCR bridge id of each person is accepted in their own workspace.
        for label in ("p", "t", "k", "e", "m"):
            _debt(cur, _ids(label)["users"], _ids(label)["workspace"])
        # A bare integer cannot say which space it came from: 21 IS an identity of p.
        # This is why no reader may ever decide ownership by user_id (static guard).
        _debt(cur, K_USERS, _ids("p")["workspace"])


def test_account_without_users_row_writes_through_both_paths(layout, monkeypatch):
    from backend.core import database
    from backend.user_product import service
    from backend.user_product.models import UserDebtCreateRequest

    s = _ids("s")
    with layout["conn"].cursor() as cur:
        _debt(cur, s["allowed"], s["workspace"])  # allowed_users-space writer (e.g. overtime)
    monkeypatch.setattr(database, "DATABASE_URL", layout["uri"])
    row = _as(s, service.create_user_debt, UserDebtCreateRequest(name="Synthetic", remaining_amount=10))
    with layout["conn"].cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email=%s", (s["email"],))
        created_users_id = cur.fetchone()[0]
        cur.execute("SELECT user_id FROM debts WHERE id=%s", (row["id"],))
        assert cur.fetchone()[0] == created_users_id  # lazily created bridge row, never another person's id
    assert created_users_id not in {users for _, users in LAYOUT.values() if users}


def test_owner_and_active_member_can_write_disabled_member_cannot(layout):
    e, s = _ids("e"), _ids("s")
    with layout["conn"].cursor() as cur:
        _debt(cur, OWNER_ID, _ids("owner")["workspace"])
        cur.execute("INSERT INTO workspace_members(workspace_id,account_id,member_role,status) VALUES(%s,%s,'member','active')",
                    (e["workspace"], s["account"]))
        _debt(cur, s["allowed"], e["workspace"])
        cur.execute("UPDATE workspace_members SET status='disabled' WHERE workspace_id=%s AND account_id=%s",
                    (e["workspace"], s["account"]))
        with pytest.raises(psycopg2.errors.CheckViolation):
            _debt(cur, s["allowed"], e["workspace"])


def test_canonical_writer_without_legacy_id_and_owner_default_fallback(layout):
    k = _ids("k")
    with layout["conn"].cursor() as cur:
        # DEFAULT 1 (the Owner) must never land in a user's workspace silently.
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute("INSERT INTO debts(name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id) "
                        "VALUES('x','other',1,1,0,%s)", (k["workspace"],))
        # Future phase: the legacy column becomes optional; ownership stays workspace_id.
        cur.execute("ALTER TABLE debts ALTER COLUMN user_id DROP NOT NULL, ALTER COLUMN user_id DROP DEFAULT")
        canonical = _debt(cur, None, k["workspace"])
    assert _audit(layout["conn"])[("debts", canonical)] == ("OK_NO_LEGACY_ID", "OK")


def test_account_deletion_still_cascades_with_the_guards(layout):
    k = _ids("k")
    with layout["conn"].cursor() as cur:
        _payment(cur, K_USERS, layout["rows"]["k_debt"], k["workspace"])
        cur.execute("DELETE FROM accounts WHERE id=%s", (k["account"],))
        cur.execute("SELECT COUNT(*) FROM debts WHERE workspace_id=%s", (k["workspace"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM debt_payments WHERE workspace_id=%s", (k["workspace"],))
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM debts")
        assert cur.fetchone()[0] == 2  # nobody else's rows were touched


ROLLBACK = ROOT / "database/rollback/20260925120000_financial_ownership_integrity_rollback.sql"


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
        cur.execute("SELECT COUNT(*) FROM pg_trigger WHERE tgname LIKE 'trg\\_%%\\_ownership_guard'")
        assert cur.fetchone()[0] == 0
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
    """K_USERS is p's allowed_users.id AND k's users.id: it cannot prove the owner."""
    conn, p = layout_unmigrated["conn"], _ids("p")
    with conn.cursor() as cur:
        debt = _debt(cur, p["allowed"], p["workspace"])
        colliding = _payment(cur, K_USERS, debt, None)
        unambiguous = _payment(cur, p["users"], debt, None)
    _apply_migration(conn)
    audit = _audit(conn)
    assert audit[("debt_payments", colliding)] == ("WORKSPACE_NULL", "NEEDS_REVIEW")
    with conn.cursor() as cur:
        cur.execute("SELECT id, workspace_id::text FROM debt_payments ORDER BY id")
        assert cur.fetchall() == [(colliding, None), (unambiguous, p["workspace"])]


def test_existing_rows_cannot_be_moved_between_workspaces(layout):
    with layout["conn"].cursor() as cur:
        with pytest.raises(psycopg2.errors.CheckViolation, match="ownership change"):
            cur.execute("UPDATE debts SET workspace_id=%s WHERE id=%s", (_ids("p")["workspace"], layout["rows"]["k_debt"]))


def test_upsert_keeps_a_row_under_review_editable(layout_unmigrated):
    """transactions/service.py rewrites workspace_id in its ON CONFLICT clause."""
    conn, k = layout_unmigrated["conn"], _ids("k")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO exchange_rates(user_id,workspace_id,rate_date,currency,exchange_rate) "
                    "VALUES(999,%s,'2026-01-02','USD',500)", (k["workspace"],))  # NEEDS_REVIEW row
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
            (k["allowed"], k["workspace"], "2026-01-02", "usd", 510, "manual"),
        )
        cur.execute("SELECT user_id, exchange_rate FROM exchange_rates")
        assert [(r[0], float(r[1])) for r in cur.fetchall()] == [(999, 510.0)]


def test_migration_aborts_when_a_mail_connection_id_is_outside_its_workspace(layout_unmigrated):
    conn, k = layout_unmigrated["conn"], _ids("k")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO finva_gmail_connections(account_id,workspace_id,legacy_user_id) VALUES(%s,%s,%s)",
                    (k["account"], k["workspace"], T_USERS))
    with pytest.raises(psycopg2.Error, match="stored legacy ids outside their workspace"):
        _apply_migration(conn)
    with conn.cursor() as cur:
        cur.execute("ROLLBACK")
        cur.execute("UPDATE finva_gmail_connections SET legacy_user_id=%s", (K_USERS,))
    _apply_migration(conn)


def test_email_bridge_ignores_case_and_surrounding_spaces(layout):
    k = _ids("k")
    with layout["conn"].cursor() as cur:
        cur.execute("UPDATE accounts SET primary_email=%s WHERE id=%s", (f"  {k['email'].upper()} ", k["account"]))
        _debt(cur, K_USERS, k["workspace"])
