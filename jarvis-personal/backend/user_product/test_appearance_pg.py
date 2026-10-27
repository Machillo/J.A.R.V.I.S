"""Personal appearance storage on a real PostgreSQL: the production `user_preferences` table.

The table comes from its migration (20260926125000_owner_legacy_schema.sql), in both states
production may be in: before 20260926130000 (legacy `user_id` filled by its default) and after it
(`user_id` optional). The statements of appearance.py must run unchanged in both, keep one row per
account and never touch another account's or workspace's rows. Synthetic values only.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")
from psycopg2.extras import RealDictCursor  # noqa: E402

from backend.auth.current_user import reset_current_user, set_current_user  # noqa: E402
from backend.core.database import PostgresCursorResult  # noqa: E402
from backend.user_product import appearance  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "database"
SCHEMA = (ROOT / "schema.sql").read_text(encoding="utf-8")
LEGACY = (ROOT / "migrations" / "20260926125000_owner_legacy_schema.sql").read_text(encoding="utf-8")
CHOICE = appearance.AppearancePreferences(theme="light", palette="grafito", accent="teal", text_size="xl", typeface="system", density="compact", surfaces="tonal")


def _table(source: str, name: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS {name} \(.*?\n\);", source, re.S)
    assert match, f"{name} moved"
    return match.group(0)


class _Conn:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        pass

    def execute(self, query, params=()):
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall() if self.cursor.description else []
        return PostgresCursorResult(rows=[dict(row) for row in rows], rowcount=self.cursor.rowcount)


@pytest.fixture(params=["user_id_default", "user_id_optional"])
def cur(request, tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"appearance_{os.getpid()}_{abs(hash(str(tmp_path) + request.param)) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    conn = psycopg2.connect(server.get_uri(name), cursor_factory=RealDictCursor)
    conn.autocommit = True
    cursor = conn.cursor()
    for table in ("allowed_users", "accounts", "workspaces"):
        cursor.execute(_table(SCHEMA, table))
    cursor.execute(_table(LEGACY, "user_preferences"))
    cursor.execute("INSERT INTO allowed_users(email, role, status) VALUES ('legacy@example.test', 'user', 'active')")
    if request.param == "user_id_default":
        cursor.execute("ALTER TABLE user_preferences ALTER COLUMN user_id SET DEFAULT 1")
    else:
        cursor.execute("ALTER TABLE user_preferences ALTER COLUMN user_id DROP NOT NULL")
    monkeypatch.setattr(appearance, "get_connection", lambda: _Conn(cursor))
    yield cursor
    conn.close()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _account(cur) -> str:
    account = str(uuid.uuid4())
    cur.execute("INSERT INTO allowed_users(email, role, status) VALUES (%s, 'user', 'active') RETURNING id", (f"{account}@example.test",))
    legacy = cur.fetchone()["id"]
    cur.execute("INSERT INTO accounts(id, legacy_allowed_user_id, primary_email, role, status) VALUES (%s, %s, %s, 'user', 'active')",
                (account, legacy, f"{account}@example.test"))
    return account


def _workspace(cur) -> str:
    workspace = str(uuid.uuid4())
    cur.execute("INSERT INTO workspaces(id, workspace_key, owner_account_id, name) VALUES (%s, %s, %s, 'Personal')",
                (workspace, f"ws-{workspace}", _account(cur)))
    return workspace


def _as(account: str, workspace: str):
    return set_current_user({"id": 1, "account_id": account, "workspace_id": workspace, "role": "owner"})


def _call(account, workspace, fn, *args):
    token = _as(account, workspace)
    try:
        return fn(*args)
    finally:
        reset_current_user(token)


def test_save_read_update_and_reset_on_the_production_table(cur):
    workspace, account = _workspace(cur), _account(cur)
    assert _call(account, workspace, appearance.get_appearance)["stored"] is False
    saved = _call(account, workspace, appearance.save_appearance, CHOICE)
    assert saved["preferences"] == CHOICE.model_dump() and saved["updated_at"]
    read = _call(account, workspace, appearance.get_appearance)
    assert read["preferences"] == CHOICE.model_dump() and read["stored"] is True
    changed = CHOICE.model_copy(update={"accent": "cian"})
    _call(account, workspace, appearance.save_appearance, changed)
    cur.execute("SELECT count(*) AS n FROM user_preferences")
    assert cur.fetchone()["n"] == 1, "an update replaces the account's row"
    assert _call(account, workspace, appearance.get_appearance)["preferences"]["accent"] == "cian"
    assert _call(account, workspace, appearance.reset_appearance)["stored"] is False
    cur.execute("SELECT preference_value FROM user_preferences")
    assert [row["preference_value"] for row in cur.fetchall()] == [{}], "a reset clears the value; no DELETE"
    assert _call(account, workspace, appearance.get_appearance)["preferences"] == appearance.DEFAULTS.model_dump()


def test_other_accounts_and_workspaces_are_untouched(cur):
    workspace, other_workspace = _workspace(cur), _workspace(cur)
    account, neighbour, stranger = (_account(cur) for _ in range(3))
    cur.execute(
        "INSERT INTO user_preferences (workspace_id, preference_key, preference_value) VALUES (%s, 'sports', '{\"f1\": true}'::jsonb)",
        (workspace,),
    )
    _call(account, workspace, appearance.save_appearance, CHOICE)
    _call(neighbour, workspace, appearance.save_appearance, appearance.DEFAULTS)
    _call(stranger, other_workspace, appearance.save_appearance, CHOICE.model_copy(update={"palette": "arena"}))
    _call(neighbour, workspace, appearance.reset_appearance)
    _call(stranger, other_workspace, appearance.reset_appearance)
    assert _call(account, workspace, appearance.get_appearance)["preferences"] == CHOICE.model_dump()
    # The same account id in another workspace is another scope too.
    assert _call(account, other_workspace, appearance.get_appearance)["stored"] is False
    cur.execute("SELECT preference_key, preference_value FROM user_preferences WHERE workspace_id = %s ORDER BY preference_key", (workspace,))
    rows = {row["preference_key"]: row["preference_value"] for row in cur.fetchall()}
    assert rows == {f"appearance.v1.account.{account}": CHOICE.model_dump(), f"appearance.v1.account.{neighbour}": {}, "sports": {"f1": True}}
