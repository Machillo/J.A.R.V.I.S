"""20260926160000 (store verification, EXPAND phase) on the production role setup.

The migration only adds structure: four store_* tables and three nullable
store_subscriptions columns. Nothing is granted: until the activation migration that
ships with the code using these tables, no runtime or public role can reach them, and
the code on main keeps working. Runs after the real 149000/150000/151000/152000, as the
non-superuser migrator (like Supabase's postgres), connecting as the real dincr_app.
Synthetic data only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.core import database
from backend.product_ops.service import has_store_entitlement
from backend.tests.test_dincr_app_role_pg import ACC_A, GUARD_BY_ROLE, ROOT, _admin_uri, _postflight, env  # noqa: F401

psycopg2 = pytest.importorskip("psycopg2")

EXPAND = ROOT / "migrations" / "20260926160000_store_verification.sql"
RETIREMENT = ROOT / "migrations" / "20260926152000_retire_offstore_billing.sql"
ROLLBACK = ROOT / "rollback" / "20260926160000_store_verification_rollback.sql"
TABLES = ("store_customer_tokens", "store_purchases", "store_purchase_conflicts", "store_revocations")
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
ACC_C = "00000000-0000-4000-8000-0000000000c1"


@pytest.fixture
def before_store_verification(env):
    """Production as it is before 160000: 149000-152000 applied, store_subscriptions as main reads it."""
    owner = env["owner"]
    # Supabase grants every new public table to its API roles by default; the
    # migration must take that back.
    owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
    owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated")
    # store_subscriptions as main reads it (the role fixture only stubs it).
    owner.execute("""ALTER TABLE store_subscriptions
                     ADD COLUMN account_id UUID UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
                     ADD COLUMN provider TEXT, ADD COLUMN plan_code TEXT, ADD COLUMN status TEXT,
                     ADD COLUMN trial_ends_at TIMESTAMPTZ, ADD COLUMN current_period_end TIMESTAMPTZ""")
    owner.execute("""INSERT INTO store_subscriptions(account_id, provider, plan_code, status, current_period_end)
                     VALUES (%s, 'apple', 'vip', 'active', %s)""", (ACC_A, datetime.now(timezone.utc) + timedelta(days=9)))
    owner.execute(GUARD_BY_ROLE.read_text(encoding="utf-8"))
    owner.execute("CREATE TABLE IF NOT EXISTS finva_beta_programs (code TEXT)")  # stubbed like the rest
    owner.execute(RETIREMENT.read_text(encoding="utf-8"))
    return env


@pytest.fixture
def expanded(before_store_verification):
    before_store_verification["owner"].execute(EXPAND.read_text(encoding="utf-8"))
    return before_store_verification


def test_the_structure_exists_with_its_keys_checks_and_indexes(expanded):
    owner = expanded["owner"]
    owner.execute("SELECT count(*) FROM unnest(%s::text[]) t WHERE to_regclass('public.' || t) IS NOT NULL", (list(TABLES),))
    assert owner.fetchone() == (4,)
    owner.execute("""SELECT column_name, is_nullable FROM information_schema.columns
                     WHERE table_schema='public' AND table_name='store_subscriptions'
                       AND column_name IN ('grace_ends_at', 'revoked_at', 'environment') ORDER BY 1""")
    assert owner.fetchall() == [("environment", "YES"), ("grace_ends_at", "YES"), ("revoked_at", "YES")]
    owner.execute("""SELECT conrelid::regclass::text, contype, pg_get_constraintdef(oid) FROM pg_constraint
                     WHERE conrelid = ANY(%s::regclass[]) ORDER BY 1, 2, 3""", (list(TABLES),))
    constraints = owner.fetchall()
    assert ("store_purchases", "p", "PRIMARY KEY (provider, purchase_key)") in constraints
    assert ("store_revocations", "p", "PRIMARY KEY (provider, transaction_id)") in constraints
    assert ("store_customer_tokens", "u", "UNIQUE (token)") in constraints
    assert ("store_purchases", "f", "FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE") in constraints
    assert ("store_purchase_conflicts", "f",
            "FOREIGN KEY (bound_account_id) REFERENCES accounts(id) ON DELETE SET NULL") in constraints
    checks = " ".join(definition for table, kind, definition in constraints if table == "store_purchases" and kind == "c")
    for allowed in ("'apple'", "'production'", "'basic'", "'annual'", "'grace_period'", "'superseded'"):
        assert allowed in checks
    assert not any(table == "store_revocations" and kind == "f" for table, kind, _ in constraints)  # outlives accounts
    owner.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'store_purchases' ORDER BY 1")
    assert ("idx_store_purchases_account",) in owner.fetchall()


def test_no_runtime_or_public_role_can_reach_the_new_tables(expanded):
    owner = expanded["owner"]
    owner.execute("SELECT relname FROM pg_class WHERE relname = ANY(%s) AND NOT relrowsecurity", (list(TABLES),))
    assert owner.fetchall() == []
    owner.execute("SELECT tablename, policyname FROM pg_policies WHERE tablename = ANY(%s)", (list(TABLES),))
    assert owner.fetchall() == []  # the dincr_app_access policies belong to the activation
    owner.execute("""SELECT r, t, p FROM unnest(%s::text[]) t, unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r,
                            unnest(%s::text[]) p
                     WHERE has_table_privilege(r, 'public.' || t, p)""", (list(TABLES), list(PRIVILEGES)))
    assert owner.fetchall() == []
    owner.execute("""SELECT r FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r
                     WHERE has_sequence_privilege(r, 'public.store_purchase_conflicts_id_seq', 'USAGE')""")
    assert owner.fetchall() == []
    app = expanded["as_app"]()
    for table in TABLES:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            app.execute(f"SELECT 1 FROM public.{table}")


@pytest.mark.parametrize("absent", ["anon", "authenticated"])
def test_each_api_role_is_revoked_even_when_the_other_is_absent(before_store_verification, tmp_path, absent):
    """No formal guarantee that both Supabase API roles exist: each is revoked on its own."""
    owner = before_store_verification["owner"]
    present = {"anon": "authenticated", "authenticated": "anon"}[absent]
    hidden = f"{absent}_absent_probe"
    admin = psycopg2.connect(_admin_uri(tmp_path / "pg"))  # the same server as the fixture's
    admin.autocommit = True
    try:
        with admin.cursor() as c:  # a rename keeps the role's OID, so its grants come back intact
            c.execute(f'ALTER ROLE "{absent}" RENAME TO "{hidden}"')
        owner.execute(EXPAND.read_text(encoding="utf-8"))
        owner.execute("""SELECT t, p FROM unnest(%s::text[]) t, unnest(%s::text[]) p
                         WHERE has_table_privilege(%s, 'public.' || t, p)""", (list(TABLES), list(PRIVILEGES), present))
        assert owner.fetchall() == []
        owner.execute("""SELECT p FROM unnest(ARRAY['USAGE', 'SELECT', 'UPDATE']) p
                         WHERE has_sequence_privilege(%s, 'public.store_purchase_conflicts_id_seq', p)""", (present,))
        assert owner.fetchall() == []
    finally:
        with admin.cursor() as c:
            c.execute(f'ALTER ROLE "{hidden}" RENAME TO "{absent}"')
        admin.close()


def test_the_postflight_holds_and_the_migration_is_idempotent(expanded):
    owner = expanded["owner"]
    owner.execute(_postflight(EXPAND))
    assert owner.fetchall() == []
    owner.execute(EXPAND.read_text(encoding="utf-8"))
    owner.execute(_postflight(EXPAND))
    assert owner.fetchall() == []


def test_the_postflight_sees_a_grant_or_a_policy(expanded):
    owner = expanded["owner"]
    owner.execute("GRANT SELECT ON TABLE public.store_revocations TO dincr_app")
    owner.execute("CREATE POLICY probe ON public.store_purchases FOR SELECT TO authenticated USING (false)")
    owner.execute(_postflight(EXPAND))
    assert sorted(owner.fetchall()) == [("dincr_app has SELECT on store_revocations",), ("policy probe on store_purchases",)]


def test_the_code_on_main_keeps_working_as_dincr_app(expanded, monkeypatch):
    app = expanded["as_app"]()
    params = app.connection.get_dsn_parameters()
    monkeypatch.setattr(database, "DATABASE_URL", f"host={params['host']} port={params['port']} "
                                                  f"dbname={params['dbname']} user=dincr_app")
    with database.get_connection() as conn:
        assert has_store_entitlement(conn, ACC_A) is True  # the entitlement reader, unchanged
        row = conn.execute("SELECT * FROM store_subscriptions WHERE account_id=%s", (ACC_A,)).fetchone()
        assert row["plan_code"] == "vip" and row["environment"] is None and row["grace_ends_at"] is None
        # The data export lists only tables the role can access: the new ones stay out.
        from backend.auth.data_export import _owned_tables
        assert not set(TABLES) & set(_owned_tables(conn))
        conn.rollback()


def test_account_deletion_cascades_through_the_new_tables_without_grants(expanded):
    owner = expanded["owner"]
    owner.execute("INSERT INTO allowed_users(id,email,role,status) VALUES(13,'13@example.test','user','active')")
    owner.execute("INSERT INTO accounts(id,legacy_allowed_user_id,primary_email) VALUES(%s,13,'13@example.test')", (ACC_C,))
    owner.execute("INSERT INTO store_customer_tokens(account_id) VALUES (%s)", (ACC_C,))
    owner.execute("""INSERT INTO store_purchases(provider,purchase_key,account_id,environment,product_id,plan_code,
                         billing_period,status,last_transaction_id,state_version)
                     VALUES ('apple','synthetic-key',%s,'production','p','vip','monthly','active','t1',1)""", (ACC_C,))
    owner.execute("""INSERT INTO store_purchase_conflicts(provider,purchase_key,bound_account_id,claimed_account_id)
                     VALUES ('apple','synthetic-key',%s,%s)""", (ACC_C, ACC_A))
    app = expanded["as_app"]()
    app.execute("DELETE FROM accounts WHERE id=%s RETURNING id", (ACC_C,))  # as main's account deletion does
    assert app.fetchone() == (ACC_C,)
    owner.execute("""SELECT (SELECT count(*) FROM store_customer_tokens), (SELECT count(*) FROM store_purchases),
                            (SELECT bound_account_id FROM store_purchase_conflicts)""")
    assert owner.fetchone() == (0, 0, None)


def test_the_rollback_removes_only_the_expand_and_refuses_while_it_matters(expanded):
    owner = expanded["owner"]
    owner.execute("INSERT INTO store_revocations(provider,transaction_id,purchase_key) VALUES ('apple','t9','k9')")
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "SV001"
    owner.execute("ROLLBACK")
    owner.execute("DELETE FROM store_revocations")
    owner.execute("GRANT SELECT ON TABLE public.store_purchases TO dincr_app")  # an activation still in place
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "SV003"
    owner.execute("ROLLBACK")
    owner.execute("REVOKE ALL ON TABLE public.store_purchases FROM dincr_app")
    owner.execute(ROLLBACK.read_text(encoding="utf-8"))
    owner.execute("SELECT count(*) FROM unnest(%s::text[]) t WHERE to_regclass('public.' || t) IS NOT NULL", (list(TABLES),))
    assert owner.fetchone() == (0,)
    owner.execute("""SELECT count(*) FROM information_schema.columns WHERE table_name='store_subscriptions'
                     AND column_name IN ('grace_ends_at', 'revoked_at', 'environment')""")
    assert owner.fetchone() == (0,)
    owner.execute("SELECT plan_code FROM store_subscriptions WHERE account_id=%s", (ACC_A,))
    assert owner.fetchone() == ("vip",)  # what existed before 160000 is untouched
