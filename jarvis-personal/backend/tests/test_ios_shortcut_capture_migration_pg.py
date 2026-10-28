"""The iOS Shortcuts capture migration (20261028120000) on a real PostgreSQL.

Applies the real file on the shared review schema (synthetic rows): postflight clean, existing
mail candidates untouched, only the backend role can read the tokens, idempotent re-run, and the
manual rollback refuses while a capture exists and restores the schema once there is none.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.tests.test_accounts_mail_strategy_pg import A, pg  # noqa: F401  (fixture)
from backend.tests.test_mail_candidate_currency_pg import admin_uri  # noqa: F401  (module fixture)

psycopg2 = pytest.importorskip("psycopg2")

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "database/migrations/20261028120000_ios_shortcut_capture.sql"
ROLLBACK = ROOT / "database/rollback/20261028120000_ios_shortcut_capture_rollback.sql"


def _block(path: Path, title: str) -> str:
    """The commented SQL after `title` in a migration header (preflight/postflight)."""
    lines, take = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"-- {title}"):
            take = True
            continue
        if take:
            if not line.startswith("--   "):
                break
            lines.append(line[len("--   "):])
    return "\n".join(lines)


def _rows(pg, sql):  # noqa: F811
    with pg.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


@pytest.fixture
def db(pg):  # noqa: F811
    with pg.cursor() as cur:
        cur.execute("ALTER TABLE finva_email_candidates ADD COLUMN IF NOT EXISTS source_record_key TEXT")
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname='dincr_app'")
        if not cur.fetchone():
            cur.execute("CREATE ROLE dincr_app NOLOGIN")
        cur.execute("INSERT INTO finva_email_messages(connection_id,account_id,workspace_id,provider_message_id) VALUES(%s,%s,%s,%s) RETURNING id",
                    (A["connection"], A["account"], A["workspace"], uuid.uuid4().hex))
        message = cur.fetchone()["id"]
        cur.execute("""INSERT INTO finva_email_candidates(email_message_id,account_id,workspace_id,transaction_date,description,amount,
                           transaction_type,category,bank,source_record_key) VALUES(%s,%s,%s,CURRENT_DATE,'COMPRA EJEMPLO',100,'expense','Compras','bac','gmail:x:0')""",
                    (message, A["account"], A["workspace"]))
    return pg


def test_preflight_apply_postflight_and_idempotent(db):
    assert _rows(db, _block(MIGRATION, "Preflight")) == []
    before = _rows(db, "SELECT id,email_message_id,source_record_key FROM finva_email_candidates")
    for _ in range(2):  # a second run changes nothing
        with db.cursor() as cur:
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
        assert _rows(db, _block(MIGRATION, "Postflight")) == []
    assert _rows(db, "SELECT id,email_message_id,source_record_key FROM finva_email_candidates") == before
    privileges = {(r["grantee"], r["privilege_type"]) for r in _rows(db, """SELECT grantee, privilege_type FROM information_schema.role_table_grants
                                                                             WHERE table_name='shortcut_tokens'""")}
    assert {("dincr_app", "SELECT"), ("dincr_app", "INSERT"), ("dincr_app", "UPDATE")} <= privileges
    assert not {grantee for grantee, _ in privileges} & {"anon", "authenticated"}


def test_the_capture_key_is_unique_per_account_for_captures_only(db):
    with db.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    insert = """INSERT INTO finva_email_candidates(account_id,workspace_id,transaction_date,description,amount,transaction_type,
                    category,bank,source_type,source_record_key) VALUES(%s,%s,CURRENT_DATE,'CAPTURA EJEMPLO',100,'expense','Compras','apple_pay',%s,%s)"""
    with db.cursor() as cur:
        cur.execute(insert, (A["account"], A["workspace"], "api", "apple_pay_shortcut:k1"))
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(insert, (A["account"], A["workspace"], "api", "apple_pay_shortcut:k1"))


def test_rollback_refuses_while_a_capture_exists_then_restores_and_reapplies(db):
    with db.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
        cur.execute("""INSERT INTO finva_email_candidates(account_id,workspace_id,transaction_date,description,amount,transaction_type,
                           category,bank,source_type,source_record_key) VALUES(%s,%s,CURRENT_DATE,'CAPTURA EJEMPLO',100,'expense','Compras','apple_pay','api','apple_pay_shortcut:k2')""",
                    (A["account"], A["workspace"]))
        with pytest.raises(psycopg2.errors.RaiseException):
            cur.execute(ROLLBACK.read_text(encoding="utf-8"))
        cur.execute("ROLLBACK")
        cur.execute("DELETE FROM finva_email_candidates WHERE email_message_id IS NULL")
        cur.execute(ROLLBACK.read_text(encoding="utf-8"))
    assert _rows(db, _block(ROLLBACK, "Postflight")) == []
    with db.cursor() as cur:
        cur.execute(MIGRATION.read_text(encoding="utf-8"))
    assert _rows(db, _block(MIGRATION, "Postflight")) == []
