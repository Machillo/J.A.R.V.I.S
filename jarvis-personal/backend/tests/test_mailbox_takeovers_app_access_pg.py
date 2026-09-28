"""20260928100000: the mailbox takeover works under the production application role.

20260926110000 creates mail_connection_takeovers, which the role migration
(20260926150000) does not grant. On the production role setup (see
test_dincr_app_role_pg), connected as dincr_app, a takeover of a stale mailbox is
refused with "permission denied" until 20260928100000 gives dincr_app exactly what
the claim runs (the same scan as test_dincr_app_grants.needed), the id sequence and
one dincr_app_access policy, and nothing to anyone else. Synthetic data only.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.core import database
from backend.tests.test_dincr_app_grants import needed
from backend.tests.test_dincr_app_role_pg import ACC_A, ACC_B, ROOT, WS_A, WS_B, _postflight, env  # noqa: F401
from backend.user_product import mail_oauth

psycopg2 = pytest.importorskip("psycopg2")

SINGLE_OWNER = ROOT / "migrations" / "20260926110000_mailbox_single_owner.sql"
ACCESS = ROOT / "migrations" / "20260928100000_mailbox_takeovers_app_access.sql"
ACCESS_ROLLBACK = ROOT / "rollback" / "20260928100000_mailbox_takeovers_app_access_rollback.sql"
TABLE, SEQUENCE = "mail_connection_takeovers", "public.mail_connection_takeovers_id_seq"
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
GMAIL = "https://www.googleapis.com/auth/gmail.readonly"


@pytest.fixture
def single_owner(env):
    """The production role setup, then 20260926110000 (after the role, as it can happen in production)."""
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


def _stale_mailbox(owner):
    """A Gmail connection of account A whose provider access was lost, with A's token."""
    owner.execute("SELECT dincr_private.mail_secret_create('synthetic-token', %s::uuid, 'Gmail')", (ACC_A,))
    secret = owner.fetchone()[0]
    owner.execute("""INSERT INTO finva_gmail_connections(account_id, workspace_id, legacy_user_id, google_email, mailbox_email,
                     mailbox_key, refresh_token_secret_id, granted_scopes, status)
                     VALUES (%s, %s, 11, 'shared@example.com', 'gmail:shared@example.com', 'email:gmail:shared@example.com',
                             %s, %s, 'reauthorization_required') RETURNING id""", (ACC_A, WS_A, secret, [GMAIL]))
    return owner.fetchone()[0], secret


def _claim_as_app(env, monkeypatch):
    """Account B claims the mailbox through the application's own connection, as dincr_app."""
    monkeypatch.setattr(database, "DATABASE_URL", env["as_app"]().connection.dsn)
    with database.get_connection() as conn:
        assert conn.execute("SELECT current_user AS role").fetchone()["role"] == "dincr_app"
        mail_oauth.claim_mailbox(conn, provider="gmail", account_id=ACC_B, workspace_id=WS_B,
                                 key="email:gmail:shared@example.com", email="gmail:shared@example.com",
                                 display="shared@example.com", is_entitled=lambda _conn, _account: True)
        conn.commit()


def test_without_this_migration_the_application_role_cannot_audit_a_takeover(single_owner, monkeypatch):
    owner = single_owner["owner"]
    assert _privileges(owner, "dincr_app") == set()
    stale_id, _secret = _stale_mailbox(owner)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        _claim_as_app(single_owner, monkeypatch)
    owner.execute("SELECT status FROM finva_gmail_connections WHERE id = %s", (stale_id,))
    assert owner.fetchone() == ("reauthorization_required",)  # the failed takeover changed nothing


def test_the_application_role_takes_over_a_stale_mailbox_and_audits_it(single_owner, monkeypatch):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    stale_id, secret = _stale_mailbox(owner)
    _claim_as_app(single_owner, monkeypatch)
    owner.execute("SELECT status, last_error FROM finva_gmail_connections WHERE id = %s", (stale_id,))
    assert owner.fetchone() == ("disabled", mail_oauth.MAILBOX_TAKEN_OVER)
    owner.execute("SELECT count(*) FROM vault.secrets WHERE id = %s", (secret,))
    assert owner.fetchone() == (0,)  # the stale token is deleted on its own account's behalf
    owner.execute(f"SELECT provider, previous_connection_id, previous_account_id::text, new_account_id::text, reason FROM {TABLE}")
    assert owner.fetchall() == [("gmail", stale_id, ACC_A, ACC_B, "access_lost")]


def test_a_live_mailbox_is_still_refused_under_the_application_role(single_owner, monkeypatch):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    stale_id, _secret = _stale_mailbox(owner)
    owner.execute("UPDATE finva_gmail_connections SET status = 'active' WHERE id = %s", (stale_id,))
    with pytest.raises(HTTPException) as refused:
        _claim_as_app(single_owner, monkeypatch)
    assert refused.value.status_code == 409 and refused.value.detail == mail_oauth.MAILBOX_UNAVAILABLE
    owner.execute(f"SELECT count(*) FROM {TABLE}")
    assert owner.fetchone() == (0,)


def test_exactly_the_access_the_code_needs_and_nothing_for_the_public_roles(single_owner):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    assert _privileges(owner, "dincr_app") == needed()[TABLE]
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


def test_the_postflight_holds_and_the_migration_is_idempotent(single_owner):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(_postflight(ACCESS))
    assert owner.fetchall() == []
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(_postflight(ACCESS))
    assert owner.fetchall() == []


@pytest.mark.parametrize(("change", "reported"), [
    ("REVOKE INSERT ON TABLE public.mail_connection_takeovers FROM dincr_app",
     "dincr_app lacks INSERT on mail_connection_takeovers"),
    ("GRANT UPDATE, DELETE ON TABLE public.mail_connection_takeovers TO dincr_app",
     "dincr_app has extra DELETE on mail_connection_takeovers|dincr_app has extra UPDATE on mail_connection_takeovers"),
    ("GRANT SELECT ON TABLE public.mail_connection_takeovers TO authenticated",
     "authenticated has extra SELECT on mail_connection_takeovers"),
    ("REVOKE USAGE ON SEQUENCE public.mail_connection_takeovers_id_seq FROM dincr_app",
     "dincr_app lacks USAGE on mail_connection_takeovers_id_seq"),
    ("DROP POLICY dincr_app_access ON public.mail_connection_takeovers",
     "missing policy dincr_app_access on mail_connection_takeovers"),
    ("ALTER TABLE public.mail_connection_takeovers DISABLE ROW LEVEL SECURITY",
     "row level security off on mail_connection_takeovers"),
])
def test_the_postflight_sees_missing_or_extra_access(single_owner, change, reported):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    owner.execute(change)
    owner.execute(_postflight(ACCESS))
    assert sorted(row[0] for row in owner.fetchall()) == sorted(reported.split("|"))


def test_it_refuses_to_run_before_the_single_owner_migration(env):
    owner = env["owner"]
    with pytest.raises(psycopg2.Error) as refused:
        owner.execute(ACCESS.read_text(encoding="utf-8"))
    assert refused.value.pgcode == "MB003"
    owner.execute("ROLLBACK")


def test_the_rollback_takes_back_only_this_access_and_keeps_the_audit(single_owner, monkeypatch):
    owner = single_owner["owner"]
    owner.execute(ACCESS.read_text(encoding="utf-8"))
    _stale_mailbox(owner)
    _claim_as_app(single_owner, monkeypatch)
    owner.execute(ACCESS_ROLLBACK.read_text(encoding="utf-8"))
    assert _privileges(owner, "dincr_app") == set()
    owner.execute(f"SELECT count(*) FROM {TABLE}")
    assert owner.fetchone() == (1,)  # no audit row is lost
    owner.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = %s", (TABLE,))
    assert owner.fetchone() == (0,)
    owner.execute(ACCESS.read_text(encoding="utf-8"))  # and it can be applied again
    owner.execute(_postflight(ACCESS))
    assert owner.fetchall() == []


def test_the_access_migration_sorts_after_the_role_and_shares_no_timestamp():
    """It must come after the migrations production already has (the latest: the store verification activation)."""
    names = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))
    assert ACCESS.name > "20260926161000_store_verification_activation.sql"
    assert [n for n in names if n[:14] == ACCESS.name[:14]] == [ACCESS.name]
