"""20260926161000 (store verification, ACTIVATION phase) after 20260926160000.

The activation gives dincr_app exactly what the store verification code runs on the
four store_* tables (the same scan as test_dincr_app_grants.needed), their id sequence
USAGE and one dincr_app_access policy each, and nothing to anyone else. It refuses to
run before 160000. Its rollback returns to the expand state without touching data.
Runs on the production role setup (see test_store_verification_expand_pg). Synthetic data only.
"""
from __future__ import annotations

import pytest

from backend.tests.test_dincr_app_grants import needed
from backend.tests.test_dincr_app_role_pg import ACC_A, ACC_B, ROOT, _postflight, env  # noqa: F401
from backend.tests.test_store_verification_expand_pg import (  # noqa: F401
    EXPAND, PRIVILEGES, ROLLBACK, TABLES, before_store_verification, expanded,
)

psycopg2 = pytest.importorskip("psycopg2")

ACTIVATION = ROOT / "migrations" / "20260926161000_store_verification_activation.sql"
ACTIVATION_ROLLBACK = ROOT / "rollback" / "20260926161000_store_verification_activation_rollback.sql"
SEQUENCE = "public.store_purchase_conflicts_id_seq"


def _privileges(cur, role):
    cur.execute("""SELECT t, p FROM unnest(%s::text[]) t, unnest(%s::text[]) p
                   WHERE has_table_privilege(%s, 'public.' || t, p)""", (list(TABLES), list(PRIVILEGES), role))
    found: dict[str, set[str]] = {}
    for table, privilege in cur.fetchall():
        found.setdefault(table, set()).add(privilege)
    return found


@pytest.fixture
def activated(expanded):
    expanded["owner"].execute(ACTIVATION.read_text(encoding="utf-8"))
    return expanded


def test_the_intermediate_state_then_exactly_the_access_the_code_needs(expanded):
    owner = expanded["owner"]
    # After 160000: schema present, RLS on, the runtime has no access.
    owner.execute("SELECT count(*) FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity", (list(TABLES),))
    assert owner.fetchone() == (4,)
    assert _privileges(owner, "dincr_app") == {}
    # After 161000: exactly what the store verification SQL runs, no more.
    owner.execute(ACTIVATION.read_text(encoding="utf-8"))
    code_needs = {table: privileges for table, privileges in needed().items() if table in TABLES}
    assert set(code_needs) == set(TABLES)
    assert _privileges(owner, "dincr_app") == code_needs
    assert _privileges(owner, "anon") == {} and _privileges(owner, "authenticated") == {}
    owner.execute("SELECT count(*) FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity", (list(TABLES),))
    assert owner.fetchone() == (4,)


def test_only_the_conflict_sequence_is_usable_and_only_by_dincr_app(activated):
    owner = activated["owner"]
    owner.execute("""SELECT r, p FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r,
                            unnest(ARRAY['USAGE', 'SELECT', 'UPDATE']) p
                     WHERE has_sequence_privilege(r, %s, p) ORDER BY 1, 2""", (SEQUENCE,))
    assert owner.fetchall() == [("dincr_app", "USAGE")]


def test_one_permissive_policy_per_table_for_dincr_app_only(activated):
    owner = activated["owner"]
    owner.execute("""SELECT tablename, policyname, permissive, roles::text[], cmd, qual, with_check FROM pg_policies
                     WHERE schemaname = 'public' AND tablename = ANY(%s) ORDER BY 1""", (list(TABLES),))
    assert owner.fetchall() == [(table, "dincr_app_access", "PERMISSIVE", ["dincr_app"], "ALL", "true", "true")
                                for table in sorted(TABLES)]


def test_the_postflight_holds_and_the_activation_is_idempotent(activated):
    owner = activated["owner"]
    owner.execute(_postflight(ACTIVATION))
    assert owner.fetchall() == []
    owner.execute(ACTIVATION.read_text(encoding="utf-8"))
    owner.execute(_postflight(ACTIVATION))
    assert owner.fetchall() == []


def test_the_postflight_sees_extra_or_missing_access(activated):
    owner = activated["owner"]
    owner.execute("GRANT DELETE ON TABLE public.store_purchases TO dincr_app")
    owner.execute("GRANT SELECT ON TABLE public.store_revocations TO authenticated")
    owner.execute("DROP POLICY dincr_app_access ON public.store_customer_tokens")
    owner.execute(_postflight(ACTIVATION))
    assert sorted(owner.fetchall()) == [
        ("authenticated has extra SELECT on store_revocations",),
        ("dincr_app has extra DELETE on store_purchases",),
        ("missing policy dincr_app_access on store_customer_tokens",),
    ]


def test_the_activation_refuses_to_run_before_the_expand(env):
    owner = env["owner"]
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(ACTIVATION.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "SV004"
    owner.execute("ROLLBACK")
    owner.execute("SELECT count(*) FROM pg_policies WHERE policyname = 'dincr_app_access' AND tablename = ANY(%s)",
                  (list(TABLES),))
    assert owner.fetchone() == (0,)


def test_the_runtime_role_can_run_the_store_sql_but_nothing_more(activated):
    app = activated["as_app"]()
    app.execute("INSERT INTO store_customer_tokens(account_id) VALUES (%s) RETURNING token", (ACC_A,))
    assert app.fetchone()[0]
    upsert = """INSERT INTO store_purchases(provider,purchase_key,account_id,environment,product_id,plan_code,
                    billing_period,status,last_transaction_id,state_version)
                VALUES ('apple','synthetic-key',%s,'production','p','vip','monthly',%s,'t1',1)
                ON CONFLICT(provider,purchase_key) DO UPDATE SET status=EXCLUDED.status RETURNING status"""
    app.execute(upsert, (ACC_A, "active"))
    app.execute(upsert, (ACC_A, "grace_period"))
    assert app.fetchone() == ("grace_period",)
    app.execute("""INSERT INTO store_purchase_conflicts(provider,purchase_key,bound_account_id,claimed_account_id)
                   VALUES ('apple','synthetic-key',%s,%s) RETURNING id""", (ACC_A, ACC_B))
    app.execute("""INSERT INTO store_revocations(provider,transaction_id,purchase_key) VALUES ('apple','t1','synthetic-key')
                   ON CONFLICT(provider,transaction_id) DO UPDATE SET reversed_at=NULL RETURNING transaction_id""")
    for statement in ("DELETE FROM store_purchases", "DELETE FROM store_customer_tokens",
                      "TRUNCATE store_revocations", "UPDATE store_customer_tokens SET token = gen_random_uuid()"):
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            app.execute(statement)


def test_the_activation_rollback_returns_to_the_expand_state_and_keeps_the_data(activated):
    owner = activated["owner"]
    owner.execute("INSERT INTO store_revocations(provider,transaction_id,purchase_key) VALUES ('apple','t9','k9')")
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(ROLLBACK.read_text(encoding="utf-8"))  # the expand rollback waits for this one
    assert refused.value.pgcode == "SV003"
    owner.execute("ROLLBACK")
    owner.execute(ACTIVATION_ROLLBACK.read_text(encoding="utf-8"))
    owner.execute(_postflight(EXPAND))
    assert owner.fetchall() == []  # schema present, RLS on, no access, no policy
    owner.execute("SELECT count(*) FROM store_revocations")
    assert owner.fetchone() == (1,)
    owner.execute(ACTIVATION_ROLLBACK.read_text(encoding="utf-8"))  # re-runnable
    owner.execute(ACTIVATION.read_text(encoding="utf-8"))  # and the activation can be applied again
    owner.execute(_postflight(ACTIVATION))
    assert owner.fetchall() == []
