"""20260928100000: runtime access to the mailbox takeover audit, on the production role setup.

20260926110000 (already in production) created mail_connection_takeovers; the role
migration (20260926150000) does not grant it. Connected as dincr_app, the audit row
the mailbox claim writes is refused until 20260928100000 gives dincr_app exactly
SELECT, INSERT, USAGE on the id sequence and one dincr_app_access policy, and nothing
to anyone else. The migration touches no row. SQL only (no runtime code); synthetic data.
"""
from __future__ import annotations

import pytest

from backend.tests.test_dincr_app_role_pg import ACC_A, ACC_B, ROOT, _postflight, env  # noqa: F401

psycopg2 = pytest.importorskip("psycopg2")

SINGLE_OWNER = ROOT / "migrations" / "20260926110000_mailbox_single_owner.sql"
ACCESS = ROOT / "migrations" / "20260928100000_mailbox_takeovers_app_access.sql"
ACCESS_ROLLBACK = ROOT / "rollback" / "20260928100000_mailbox_takeovers_app_access_rollback.sql"
TABLE, SEQUENCE = "mail_connection_takeovers", "public.mail_connection_takeovers_id_seq"
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
AUDIT_ROW = f"INSERT INTO public.{TABLE}(provider, previous_account_id, new_account_id, reason) VALUES ('gmail', %s, %s, 'access_lost')"


@pytest.fixture
def single_owner(env):
    """The production role setup, then 20260926110000 (applied after the role, as in production)."""
    owner = env["owner"]
    # Columns of the production finva_gmail_connections that the ownership fixture omits.
    owner.execute("""ALTER TABLE finva_gmail_connections
                     ADD COLUMN IF NOT EXISTS google_email TEXT,
                     ADD COLUMN IF NOT EXISTS granted_scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                     ADD COLUMN IF NOT EXISTS history_id TEXT, ADD COLUMN IF NOT EXISTS watch_expiration TIMESTAMPTZ,
                     ADD COLUMN IF NOT EXISTS initial_scan_page_token TEXT, ADD COLUMN IF NOT EXISTS last_error TEXT,
                     ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ""")
    owner.execute(SINGLE_OWNER.read_text(encoding="utf-8"))
    return env


def _privileges(cur, role):
    cur.execute("SELECT p FROM unnest(%s::text[]) p WHERE has_table_privilege(%s, %s, p)",
                (list(PRIVILEGES), role, f"public.{TABLE}"))
    return {row[0] for row in cur.fetchall()}


def _rows(owner):
    owner.execute(f"SELECT id, provider, previous_account_id::text, new_account_id::text, reason, created_at FROM {TABLE} ORDER BY id")
    return owner.fetchall()


def test_without_the_migration_dincr_app_cannot_write_or_read_the_audit(single_owner):
    owner, app = single_owner["owner"], single_owner["as_app"]()
    assert _privileges(owner, "dincr_app") == set()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        app.execute(AUDIT_ROW, (ACC_A, ACC_B))
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        app.execute(f"SELECT count(*) FROM {TABLE}")


def test_with_the_migration_dincr_app_writes_and_reads_the_audit_through_rls(single_owner):
    owner, app = single_owner["owner"], single_owner["as_app"]()
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    app.execute(AUDIT_ROW + " RETURNING id", (ACC_A, ACC_B))  # nextval on the id sequence
    assert app.fetchone()[0] >= 1
    app.execute(f"SELECT provider, previous_account_id::text, new_account_id::text, reason FROM {TABLE}")
    assert app.fetchall() == [("gmail", ACC_A, ACC_B, "access_lost")]  # the policy lets the role see its rows
    for statement in (f"UPDATE {TABLE} SET reason = 'plan_inactive'", f"DELETE FROM {TABLE}", f"TRUNCATE {TABLE}",
                      f"SELECT setval('{SEQUENCE}', 1000)"):
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            app.execute(statement)


def test_exactly_select_insert_and_sequence_usage_and_nothing_for_the_public_roles(single_owner):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    assert _privileges(owner, "dincr_app") == {"SELECT", "INSERT"}
    assert _privileges(owner, "anon") == set() and _privileges(owner, "authenticated") == set()
    owner.execute("""SELECT r, p FROM unnest(ARRAY['anon', 'authenticated', 'dincr_app']) r,
                            unnest(ARRAY['USAGE', 'SELECT', 'UPDATE']) p
                     WHERE has_sequence_privilege(r, %s, p) ORDER BY 1, 2""", (SEQUENCE,))
    assert owner.fetchall() == [("dincr_app", "USAGE")]
    owner.execute("""SELECT policyname, permissive, roles::text[], cmd, qual, with_check FROM pg_policies
                     WHERE schemaname = 'public' AND tablename = %s""", (TABLE,))
    assert owner.fetchall() == [("dincr_app_access", "PERMISSIVE", ["dincr_app"], "ALL", "true", "true")]
    owner.execute("SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (f"public.{TABLE}",))
    assert owner.fetchone() == (True,)


def test_the_migration_and_its_rollback_touch_no_audit_row(single_owner):
    owner = single_owner["owner"]
    owner.execute(AUDIT_ROW, (ACC_A, ACC_B))
    before = _rows(owner)
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    assert _rows(owner) == before
    owner.execute(ACCESS_ROLLBACK.read_text(encoding="utf-8"))
    assert _rows(owner) == before


def test_the_postflight_holds_and_the_migration_is_idempotent(single_owner):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(_postflight(ACCESS))
    assert owner.fetchall() == []
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(_postflight(ACCESS))
    assert owner.fetchall() == []


@pytest.mark.parametrize(("change", "reported"), [
    (f"REVOKE INSERT ON TABLE public.{TABLE} FROM dincr_app", f"dincr_app lacks INSERT on {TABLE}"),
    (f"GRANT UPDATE, DELETE ON TABLE public.{TABLE} TO dincr_app",
     f"dincr_app has extra DELETE on {TABLE}|dincr_app has extra UPDATE on {TABLE}"),
    (f"GRANT SELECT ON TABLE public.{TABLE} TO anon", f"anon has extra SELECT on {TABLE}"),
    (f"GRANT SELECT ON TABLE public.{TABLE} TO authenticated", f"authenticated has extra SELECT on {TABLE}"),
    (f"REVOKE USAGE ON SEQUENCE {SEQUENCE} FROM dincr_app", "dincr_app lacks USAGE on mail_connection_takeovers_id_seq"),
    (f"DROP POLICY dincr_app_access ON public.{TABLE}", f"missing policy dincr_app_access on {TABLE}"),
    (f"ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY", f"row level security off on {TABLE}"),
])
def test_the_postflight_sees_missing_or_extra_access(single_owner, change, reported):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(change)
    owner.execute(_postflight(ACCESS))
    assert sorted(row[0] for row in owner.fetchall()) == sorted(reported.split("|"))


def test_it_refuses_to_run_before_20260926110000(env):
    owner = env["owner"]
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(ACCESS.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "MB003"
    owner.execute("ROLLBACK")


def test_the_rollback_takes_back_only_this_access(single_owner):
    owner = single_owner["owner"]
    owner.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
    policies_before = owner.fetchone()[0]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(ACCESS_ROLLBACK.read_text(encoding="utf-8"))
    assert _privileges(owner, "dincr_app") == set()
    owner.execute("SELECT has_sequence_privilege('dincr_app', %s, 'USAGE')", (SEQUENCE,))
    assert owner.fetchone() == (False,)
    owner.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'")
    assert owner.fetchone() == (policies_before,)  # every other table keeps its dincr_app_access
    owner.execute("SELECT has_table_privilege('dincr_app', 'public.finva_gmail_connections', 'UPDATE')")
    assert owner.fetchone() == (True,)  # the role's other grants are untouched
    owner.execute(ACCESS.read_text(encoding="utf-8"))  # and it can be applied again
    owner.execute(_postflight(ACCESS))
    assert owner.fetchall() == []
