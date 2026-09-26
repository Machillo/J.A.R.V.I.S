"""The dedicated application role (dincr_app) on PostgreSQL, connected as that role.

Builds the identity baseline, the ownership fixture and guard (#245), a synthetic
Vault, the mail secret boundary (20260926149000) and the role (20260926150000).
Tables of the production schema that the fixture lacks are created as stubs: the
role's privileges are what is under test here. Synthetic data only.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / "database"
BASELINE = ROOT / "baseline/v1_identity_ownership.sql"
FIXTURE = HERE / "fixtures/ownership_financial_tables.sql"
OWNERSHIP = ROOT / "migrations/20260925140000_financial_ownership_integrity.sql"
VAULT_STUB = HERE / "fixtures/vault_stub.sql"
BOUNDARY = ROOT / "migrations/20260926149000_mail_secret_boundary.sql"
ROLE = ROOT / "migrations/20260926150000_dincr_app_role.sql"
GUARD_BY_ROLE = ROOT / "migrations/20260926151000_guard_by_app_role.sql"
ROLE_ROLLBACK = ROOT / "rollback/20260926150000_dincr_app_role_rollback.sql"

WS_A, WS_B = "00000000-0000-4000-8000-00000000000a", "00000000-0000-4000-8000-00000000000b"
ACC_A, ACC_B = "00000000-0000-4000-8000-0000000000a1", "00000000-0000-4000-8000-0000000000b1"


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
    return pgserver.get_server(os.environ.get("DINCR_PGSERVER_DIR") or data_dir, cleanup_mode="stop").get_uri()


def _with(uri: str, database: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(uri)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _granted_tables() -> list[str]:
    block = ROLE.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"ON TABLE public\.(\w+) TO dincr_app", block)))


@pytest.fixture
def env(tmp_path):
    admin_uri = _admin_uri(tmp_path / "pg")
    name = f"approle_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as c:
        for role in ("anon", "authenticated"):
            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not c.fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute(f'CREATE DATABASE "{name}"')
    uri = _with(admin_uri, name)
    owner = psycopg2.connect(uri, application_name="psql")
    owner.autocommit = True
    cur = owner.cursor()
    cur.execute(BASELINE.read_text(encoding="utf-8"))
    cur.execute(FIXTURE.read_text(encoding="utf-8"))
    cur.execute(OWNERSHIP.read_text(encoding="utf-8"))
    cur.execute(VAULT_STUB.read_text(encoding="utf-8"))
    cur.execute("""CREATE TABLE IF NOT EXISTS mail_oauth_flows (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                   account_id UUID, pending_secret_id UUID)""")
    cur.execute("ALTER TABLE finva_gmail_connections ADD COLUMN IF NOT EXISTS account_id UUID, "
                "ADD COLUMN IF NOT EXISTS refresh_token_secret_id UUID")
    for table in _granted_tables():
        cur.execute(f"CREATE TABLE IF NOT EXISTS public.{table} (id BIGSERIAL PRIMARY KEY, workspace_id UUID)")
        cur.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    for allowed, account, workspace in ((11, ACC_A, WS_A), (12, ACC_B, WS_B)):
        cur.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(%s,%s,'user','active')", (allowed, f"{allowed}@example.test"))
        cur.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email) VALUES(%s,%s,%s)", (account, allowed, f"{allowed}@example.test"))
        cur.execute("""INSERT INTO workspaces(id,workspace_key,owner_account_id,name,workspace_type)
                       VALUES(%s,%s,%s,'Personal','personal')""", (workspace, f"personal:{account}", account))
        cur.execute("""INSERT INTO workspace_members(workspace_id,account_id,member_role,status)
                       VALUES(%s,%s,'owner','active')""", (workspace, account))
    cur.execute(BOUNDARY.read_text(encoding="utf-8"))
    cur.execute(ROLE.read_text(encoding="utf-8"))
    connections = [owner]

    def as_app(application_name="dincr-backend"):
        conn = psycopg2.connect(uri, user="dincr_app", application_name=application_name)
        conn.autocommit = True
        connections.append(conn)
        return conn.cursor()

    try:
        yield {"owner": cur, "as_app": as_app}
    finally:
        for conn in connections:
            conn.close()
        with admin.cursor() as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _postflight(path: Path) -> str:
    tail = path.read_text(encoding="utf-8").split("-- Postflight (read-only)")[-1]
    return "\n".join(line[3:] for line in tail.splitlines()[1:] if line.startswith("-- "))


def _debt(cur, workspace):
    legacy = 11 if workspace == WS_A else 12  # the workspace owner's legacy id (the column is still required here)
    cur.execute("""INSERT INTO debts(user_id,name,debt_type,total_amount,remaining_amount,monthly_payment,workspace_id)
                   VALUES(%s,'Synthetic','other',1000,800,100,%s) RETURNING id""", (legacy, workspace))
    return cur.fetchone()[0]


def test_postflights_hold_and_the_migration_is_idempotent(env):
    owner = env["owner"]
    owner.execute(ROLE.read_text(encoding="utf-8"))
    for path in (BOUNDARY, ROLE):
        owner.execute(_postflight(path))
        assert owner.fetchall() == [], path.name


@pytest.mark.parametrize("statement", [
    "CREATE TABLE public.probe(id int)",
    "ALTER TABLE public.debts ADD COLUMN IF NOT EXISTS probe int",
    "CREATE SCHEMA probe",
    "SELECT setval('public.debts_id_seq', 1)",
    "SELECT * FROM vault.secrets",
    "SELECT * FROM vault.decrypted_secrets",
    "SELECT count(*) FROM public.financial_ownership_delete_log",
    "SELECT dincr_private.mail_secret_owned('x', gen_random_uuid())",
    "TRUNCATE public.debts",
])
def test_the_application_role_has_no_ddl_and_no_general_access(env, statement):
    app = env["as_app"]()
    with pytest.raises(psycopg2.Error) as denied:
        app.execute(statement)
    assert denied.value.pgcode == "42501"


def test_the_application_role_reads_and_writes_granted_tables_through_rls(env):
    app = env["as_app"]()
    debt = _debt(app, WS_A)
    app.execute("UPDATE debts SET remaining_amount = 700 WHERE id = %s AND workspace_id = %s", (debt, WS_A))
    app.execute("SELECT remaining_amount FROM debts WHERE id = %s", (debt,))
    assert float(app.fetchone()[0]) == 700.0


def test_mail_secrets_are_reachable_only_for_their_own_account(env):
    app = env["as_app"]()
    app.execute("SELECT dincr_private.mail_secret_create('token-a', %s::uuid, 'Gmail')", (ACC_A,))
    secret = app.fetchone()[0]
    app.execute("SELECT dincr_private.mail_secret_read(%s::uuid, %s::uuid)", (secret, ACC_A))
    assert app.fetchone() == ("token-a",)
    for statement, params in (("SELECT dincr_private.mail_secret_read(%s::uuid, %s::uuid)", (secret, ACC_B)),
                              ("SELECT dincr_private.mail_secret_delete(ARRAY[%s::uuid], %s::uuid)", (secret, ACC_B))):
        with pytest.raises(psycopg2.Error) as refused:
            app.execute(statement, params)
        assert refused.value.pgcode == "42501"
    with pytest.raises(psycopg2.Error):
        app.execute("SELECT dincr_private.mail_secret_create('x', %s::uuid, 'Other')", (ACC_A,))
    app.execute("SELECT dincr_private.mail_secret_read(gen_random_uuid(), %s::uuid)", (ACC_A,))
    assert app.fetchone() == (None,)  # absent: NULL, like the LEFT JOIN it replaces
    app.execute("SELECT dincr_private.mail_secret_delete(ARRAY[%s::uuid], %s::uuid)", (secret, ACC_A))
    assert app.fetchone() == (1,)


def test_tokens_created_before_the_rename_still_belong_to_their_account(env):
    owner, app = env["owner"], env["as_app"]()
    owner.execute("SELECT vault.create_secret('legacy', NULL, %s)", (f"FINVA Gmail refresh token for account {ACC_A}",))
    secret = owner.fetchone()[0]
    app.execute("SELECT dincr_private.mail_secret_read(%s::uuid, %s::uuid)", (secret, ACC_A))
    assert app.fetchone() == ("legacy",)


def test_the_public_api_roles_cannot_reach_the_boundary(env):
    owner = env["owner"]
    owner.execute("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname = 'dincr_private'
                       AND (has_function_privilege('anon', p.oid, 'EXECUTE')
                            OR has_function_privilege('authenticated', p.oid, 'EXECUTE'))""")
    assert owner.fetchone() == (0,)


def test_the_delete_guard_recognises_the_application_by_its_login_role(env):
    owner = env["owner"]
    app = env["as_app"]("anything")  # application_name is not the boundary any more
    debt = _debt(app, WS_A)
    app.execute("DELETE FROM debts WHERE id = %s", (debt,))
    owner.execute("SELECT db_role FROM financial_ownership_delete_log ORDER BY id DESC LIMIT 1")
    assert owner.fetchone() == ("dincr_app",)

    # Transitional (150000): the old application_name rule still admits the owner role.
    debt = _debt(owner, WS_A)
    owner.execute("SET application_name = 'dincr-backend'")
    owner.execute("DELETE FROM debts WHERE id = %s", (debt,))

    # After 151000 only the login role counts: the same claim is refused.
    owner.execute(_postflight(GUARD_BY_ROLE))
    assert owner.fetchall() == [("guard still trusts application_name",)]  # the check sees the old rule
    owner.execute(GUARD_BY_ROLE.read_text(encoding="utf-8"))
    owner.execute(_postflight(GUARD_BY_ROLE))
    assert owner.fetchall() == []
    debt = _debt(owner, WS_A)
    with pytest.raises(psycopg2.Error, match="outside the declared workspace"):
        owner.execute("DELETE FROM debts WHERE id = %s", (debt,))
    app.execute("DELETE FROM debts WHERE id = %s", (debt,))


def test_a_mislabelled_live_token_stops_the_boundary_migration(env):
    owner = env["owner"]
    owner.execute("SELECT vault.create_secret('t', NULL, %s)", (f"DINCR Gmail refresh token for account {ACC_B}",))
    secret = owner.fetchone()[0]
    owner.execute("INSERT INTO mail_oauth_flows(account_id, pending_secret_id) VALUES (%s, %s)", (ACC_A, secret))
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(BOUNDARY.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "APP02"


def test_the_rollback_removes_the_role(env):
    owner = env["owner"]
    owner.execute(ROLE_ROLLBACK.read_text(encoding="utf-8"))
    owner.execute("SELECT count(*) FROM pg_roles WHERE rolname = 'dincr_app'")
    assert owner.fetchone() == (0,)
    owner.execute("SELECT count(*) FROM pg_policies WHERE policyname = 'dincr_app_access'")
    assert owner.fetchone() == (0,)
    owner.execute(ROLE.read_text(encoding="utf-8"))  # and it can be applied again
