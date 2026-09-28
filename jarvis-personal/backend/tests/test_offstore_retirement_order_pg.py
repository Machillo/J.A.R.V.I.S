"""A database rebuilt from the migrations, in file-name order, retires off-store billing last.

20260926150000_dincr_app_role requires billing_orders and billing_subscriptions to
exist (APP03) and grants them to dincr_app; 149000, 150000 and 151000 are applied in
production. The retirement of those tables must therefore sort after them, so that
walking database/migrations in name order (a rebuild) never drops a table a later
migration still expects. The real files run here, as a non-superuser migrator like
Supabase's postgres. Synthetic data only.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from backend.tests.test_dincr_app_role_pg import (
    BASELINE, FIXTURE, OWNERSHIP, VAULT_STUB, _admin_uri, _granted_tables, _postflight, _with,
)

psycopg2 = pytest.importorskip("psycopg2")

MIGRATIONS = Path(__file__).resolve().parents[2] / "database" / "migrations"
RETIREMENT = MIGRATIONS / "20260926152000_retire_offstore_billing.sql"
BILLING_ORIGINAL = MIGRATIONS / "20260910_finva_beta_product_ops.sql"
SEQUENCE = ("20260926149000_mail_secret_boundary.sql", "20260926150000_dincr_app_role.sql",
            "20260926151000_guard_by_app_role.sql", RETIREMENT.name)
DROPS = re.compile(r"^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(\w+)", re.I | re.M)


def test_no_migration_drops_a_table_that_a_later_migration_still_needs():
    """File-name order is the rebuild order: a retirement sorts after the role migration
    that requires and grants its tables (150000), and after 151000."""
    role = MIGRATIONS / "20260926150000_dincr_app_role.sql"
    required = set(re.findall(r"'(\w+)'", role.read_text(encoding="utf-8").split("WHERE to_regclass")[0]))
    ordered = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    for path in MIGRATIONS.glob("*.sql"):
        dropped = set(t.lower() for t in DROPS.findall(path.read_text(encoding="utf-8"))) & required
        if dropped:
            assert ordered.index(path.name) > ordered.index("20260926151000_guard_by_app_role.sql"), (
                f"{path.name} drops {sorted(dropped)}, which 20260926150000 requires: it must sort after 151000")
    assert [name for name in ordered if name in SEQUENCE] == list(SEQUENCE)


@pytest.fixture
def rebuilt(tmp_path):
    admin_uri = _admin_uri(tmp_path / "pg")
    name = f"rebuild_{uuid.uuid4().hex[:12]}"
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    with admin.cursor() as c:
        for role in ("anon", "authenticated"):
            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not c.fetchone():
                c.execute(f'CREATE ROLE "{role}" NOLOGIN')
        c.execute("SELECT 1 FROM pg_roles WHERE rolname='dincr_migrator'")
        if not c.fetchone():
            c.execute("CREATE ROLE dincr_migrator LOGIN NOSUPERUSER CREATEROLE CREATEDB")
        c.execute("SELECT 1 FROM pg_roles WHERE rolname='dincr_app'")
        if c.fetchone():
            c.execute("DROP ROLE dincr_app")
        c.execute(f'CREATE DATABASE "{name}" OWNER dincr_migrator')
    owner = psycopg2.connect(_with(admin_uri, name), user="dincr_migrator", application_name="psql")
    owner.autocommit = True
    cur = owner.cursor()
    cur.execute(BASELINE.read_text(encoding="utf-8"))
    cur.execute(FIXTURE.read_text(encoding="utf-8"))
    cur.execute(OWNERSHIP.read_text(encoding="utf-8"))
    cur.execute(VAULT_STUB.read_text(encoding="utf-8"))
    cur.execute(BILLING_ORIGINAL.read_text(encoding="utf-8"))  # the real off-store billing tables
    cur.execute("INSERT INTO finva_beta_programs(code) VALUES ('beta-2026-01') ON CONFLICT DO NOTHING")
    cur.execute("""CREATE TABLE IF NOT EXISTS mail_oauth_flows (id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                   account_id UUID, pending_secret_id UUID)""")
    cur.execute("ALTER TABLE finva_gmail_connections ADD COLUMN IF NOT EXISTS account_id UUID, "
                "ADD COLUMN IF NOT EXISTS refresh_token_secret_id UUID")
    for table in _granted_tables():  # other tables of the production schema, as stubs
        cur.execute(f"CREATE TABLE IF NOT EXISTS public.{table} (id BIGSERIAL PRIMARY KEY, workspace_id UUID)")
    try:
        yield cur
    finally:
        owner.close()
        with admin.cursor() as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            c.execute("DROP ROLE IF EXISTS dincr_app")
        admin.close()


def _present(cur, tables=("billing_orders", "billing_subscriptions", "finva_beta_programs")):
    cur.execute("SELECT count(*) FROM unnest(%s::text[]) t WHERE to_regclass('public.' || t) IS NOT NULL", (list(tables),))
    return cur.fetchone()[0]


def test_a_rebuild_in_name_order_runs_the_role_migrations_then_the_retirement(rebuilt):
    ordered = sorted(p for p in MIGRATIONS.glob("*.sql") if p.name in SEQUENCE)
    assert [p.name for p in ordered] == list(SEQUENCE)
    for path in ordered:
        rebuilt.execute(path.read_text(encoding="utf-8"))  # 150000 would abort APP03 if the tables were gone
        if path.name in SEQUENCE[1:3]:
            rebuilt.execute(_postflight(path))
            assert rebuilt.fetchall() == [], path.name
    assert _present(rebuilt) == 0
    rebuilt.execute("""SELECT count(*) FROM information_schema.role_table_grants
                       WHERE grantee = 'dincr_app' AND table_name IN ('billing_orders', 'billing_subscriptions')""")
    assert rebuilt.fetchone()[0] == 0


def test_bl001_still_refuses_after_the_role_migrations(rebuilt):
    """The same gate as before the rename: any off-store billing row, and nothing is dropped."""
    for name in SEQUENCE[:3]:
        rebuilt.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
    account = "00000000-0000-4000-8000-0000000000f1"
    rebuilt.execute("INSERT INTO accounts(id, primary_email) VALUES (%s, 'bl001@example.test')", (account,))
    rebuilt.execute("INSERT INTO billing_subscriptions(account_id, plan_code, status) VALUES (%s, 'vip', 'active')", (account,))
    with pytest.raises(psycopg2.Error) as refused:
        rebuilt.execute(RETIREMENT.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "BL001"
    rebuilt.execute("ROLLBACK")
    assert _present(rebuilt) == 3
