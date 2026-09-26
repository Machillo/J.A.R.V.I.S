"""Calendar and fixed-expense reminders are read by workspace, never through the legacy user_id.

Runs the real queries on PostgreSQL (embedded pgserver). Synthetic data only: two
workspaces, rows with a legacy user_id, with a user_id from the other id space and
with none at all. Every reminder lands in the workspace that owns its source row.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.core import database  # noqa: E402
from backend.notifications import service  # noqa: E402

WS_A, WS_B = str(uuid.uuid4()), str(uuid.uuid4())
SCHEMA = """
CREATE TABLE allowed_users (id BIGINT PRIMARY KEY, email TEXT);
CREATE TABLE workspaces (id UUID PRIMARY KEY);
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL REFERENCES workspaces(id),
    title TEXT, event_date TEXT);
CREATE TABLE fixed_expenses (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name TEXT, expected_amount NUMERIC, due_day INT, reminder_days INT, is_active BOOLEAN DEFAULT TRUE);
CREATE TABLE notification_jobs (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT, workspace_id UUID NOT NULL, title TEXT, body TEXT,
    category TEXT, scheduled_at TIMESTAMPTZ, reference_type TEXT, reference_id TEXT, dedupe_key TEXT,
    payload JSONB, status TEXT DEFAULT 'pending');
CREATE UNIQUE INDEX ON notification_jobs(workspace_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
"""


@pytest.fixture
def cur(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"reminders_{uuid.uuid4().hex[:12]}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    c = conn.cursor()
    c.execute(SCHEMA)
    c.execute("INSERT INTO allowed_users VALUES (11, 'a@example.test')")  # only A has a legacy login row
    c.execute("INSERT INTO workspaces VALUES (%s), (%s)", (WS_A, WS_B))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    try:
        yield c
    finally:
        conn.close()
        with admin.cursor() as a:
            a.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


def _jobs(cur, category):
    cur.execute("SELECT workspace_id::text, user_id, reference_id FROM notification_jobs WHERE category=%s ORDER BY id",
                (category,))
    return cur.fetchall()


def test_calendar_reminders_follow_the_workspace(cur):
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    cur.execute("""INSERT INTO events(user_id, workspace_id, title, event_date) VALUES
                   (11, %s, 'A', %s), (NULL, %s, 'B', %s), (99, %s, 'B2', %s) RETURNING id""",
                (WS_A, soon, WS_B, soon, WS_B, soon))
    a, b, b2 = (row[0] for row in cur.fetchall())
    assert service.enqueue_calendar_reminders() == 6
    jobs = _jobs(cur, "calendar")
    assert {(ws, ref) for ws, _uid, ref in jobs} == {(WS_A, str(a)), (WS_B, str(b)), (WS_B, str(b2))}
    assert {uid for ws, uid, ref in jobs if ref == str(b)} == {None}
    assert service.enqueue_calendar_reminders() == 0  # idempotent


def test_fixed_expense_reminders_are_created_in_the_owning_workspace(cur):
    cur.execute("""INSERT INTO fixed_expenses(user_id, workspace_id, name, expected_amount, due_day, reminder_days)
                   VALUES (11, %s, 'Rent', 100, 28, 3), (NULL, %s, 'Phone', NULL, 28, 3) RETURNING id""", (WS_A, WS_B))
    a, b = (row[0] for row in cur.fetchall())
    created = service.enqueue_fixed_expense_reminders()
    jobs = _jobs(cur, "fixed_expense")
    assert created == len(jobs) > 0
    assert {(ws, ref) for ws, _uid, ref in jobs} == {(WS_A, str(a)), (WS_B, str(b))}
    assert {uid for ws, uid, _ref in jobs if ws == WS_B} == {None}
    assert service.enqueue_fixed_expense_reminders() == 0  # idempotent
