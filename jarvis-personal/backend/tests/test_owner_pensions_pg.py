"""The Owner's pension statement on a real PostgreSQL: it fills the preference, once, and only his."""
from __future__ import annotations

import pytest

from backend.tests.test_financial_ownership_integrity_pg import _create_database, admin_uri  # noqa: F401
from backend.tests.test_pending_conversion_pg import A, B, _seed

psycopg2 = pytest.importorskip("psycopg2")

TABLE = """CREATE TABLE IF NOT EXISTS user_preferences (id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, preference_key TEXT NOT NULL,
preference_value JSONB, updated_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(workspace_id, preference_key))"""


@pytest.fixture
def conn_uri(admin_uri, monkeypatch):  # noqa: F811
    from backend.core import database

    uri, conn, drop = _create_database(admin_uri, _seed)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    with conn.cursor() as cur:
        cur.execute(TABLE)
    try:
        yield conn
    finally:
        drop()


def _stored(conn, who):
    with conn.cursor() as cur:
        cur.execute("SELECT preference_value FROM user_preferences WHERE workspace_id=%s AND preference_key='retirement'", (who["workspace"],))
        row = cur.fetchone()
    return row[0] if row else None


def test_a_statement_is_stored_once_and_only_in_its_workspace(conn_uri):
    from backend.core.database import get_connection
    from backend.user_product import owner_pensions as op

    statement = {"rop_balance": 1000.5, "fcl_balance": 20.25, "month": "2026-09"}
    with get_connection() as conn:
        assert op.apply_statement(conn, A["workspace"], statement) is True
        conn.commit()
    stored = _stored(conn_uri, A)
    assert stored["rop_balance"] == 1000.5 and stored["fcl_balance"] == 20.25 and stored["pensions_as_of"] == "2026-09"
    assert _stored(conn_uri, B) is None, "another workspace is untouched"
    with get_connection() as conn:
        assert op.apply_statement(conn, A["workspace"], {**statement, "rop_balance": 1}) is False
        conn.commit()
    assert _stored(conn_uri, A)["rop_balance"] == 1000.5
    with get_connection() as conn:
        assert op.apply_statement(conn, A["workspace"], {"rop_balance": 2000.0, "fcl_balance": None, "month": "2026-10"}) is True
        conn.commit()
    newer = _stored(conn_uri, A)
    assert newer["rop_balance"] == 2000 and newer["fcl_balance"] == 20.25 and newer["pensions_as_of"] == "2026-10"
