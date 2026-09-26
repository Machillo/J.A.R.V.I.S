"""Calendar and fixed-expense reminders are read by workspace, never through the legacy user_id.

Runs the real queries on PostgreSQL (embedded pgserver) with the production shape of
notification_jobs.user_id: a foreign key to allowed_users, NOT NULL before migration
20260926130000 and nullable after it. Synthetic data only: two workspaces, rows
with a valid legacy id, with an id from the other legacy space and with none.
Every reminder lands in the workspace that owns its source row, and a row the job
table refuses is skipped without stopping the others.
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
CREATE TABLE notification_subscriptions (
    id BIGSERIAL PRIMARY KEY, workspace_id UUID NOT NULL, enabled BOOLEAN DEFAULT TRUE);
CREATE TABLE notification_jobs (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT REFERENCES allowed_users(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL, title TEXT, body TEXT, category TEXT, scheduled_at TIMESTAMPTZ,
    reference_type TEXT, reference_id TEXT, dedupe_key TEXT, payload JSONB, status TEXT DEFAULT 'pending',
    sent_at TIMESTAMPTZ, last_error TEXT, updated_at TIMESTAMPTZ);
CREATE UNIQUE INDEX ON notification_jobs(workspace_id, dedupe_key) WHERE dedupe_key IS NOT NULL;
"""


class _Cursor(psycopg2.extensions.cursor):
    required = True


@pytest.fixture(params=["user_id required", "user_id optional"])
def cur(request, tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"reminders_{uuid.uuid4().hex[:12]}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    c = conn.cursor(cursor_factory=_Cursor)
    c.execute(SCHEMA)
    if request.param == "user_id required":  # production before 20260926130000
        c.execute("ALTER TABLE notification_jobs ALTER COLUMN user_id SET NOT NULL")
    c.execute("INSERT INTO allowed_users VALUES (11, 'a@example.test')")
    c.execute("INSERT INTO workspaces VALUES (%s), (%s)", (WS_A, WS_B))
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    c.required = request.param == "user_id required"
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


def test_calendar_reminders_follow_the_workspace_and_skip_refused_rows(cur):
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    cur.execute("""INSERT INTO events(user_id, workspace_id, title, event_date) VALUES
                   (99, %s, 'other id space', %s), (11, %s, 'A', %s), (NULL, %s, 'B', %s) RETURNING id""",
                (WS_A, soon, WS_A, soon, WS_B, soon))
    _other, a, b = (row[0] for row in cur.fetchall())
    created = service.enqueue_calendar_reminders()
    expected = {(WS_A, str(a))} | (set() if cur.required else {(WS_B, str(b))})
    assert {(ws, ref) for ws, _uid, ref in _jobs(cur, "calendar")} == expected
    assert created == 2 * len(expected)
    assert service.enqueue_calendar_reminders() == 0  # idempotent


def test_fixed_expense_reminders_are_created_in_the_owning_workspace(cur):
    cur.execute("""INSERT INTO fixed_expenses(user_id, workspace_id, name, expected_amount, due_day, reminder_days)
                   VALUES (99, %s, 'Other', 1, 28, 3), (11, %s, 'Rent', 100, 28, 3), (NULL, %s, 'Phone', NULL, 28, 3)
                   RETURNING id""", (WS_A, WS_A, WS_B))
    _other, a, b = (row[0] for row in cur.fetchall())
    created = service.enqueue_fixed_expense_reminders()
    jobs = _jobs(cur, "fixed_expense")
    expected = {(WS_A, str(a))} | (set() if cur.required else {(WS_B, str(b))})
    assert created == len(jobs) > 0
    assert {(ws, ref) for ws, _uid, ref in jobs} == expected
    assert service.enqueue_fixed_expense_reminders() == 0  # idempotent


def test_a_stale_job_is_never_delivered(cur, monkeypatch):
    monkeypatch.setattr(service, "enqueue_calendar_reminders", lambda: 0)
    monkeypatch.setattr(service, "enqueue_fixed_expense_reminders", lambda: 0)
    import backend.sports.service as sports
    monkeypatch.setattr(sports, "enqueue_owner_sports_digest_notifications", lambda: {"status": "OK"})
    now = datetime.now(timezone.utc)
    cur.execute("""INSERT INTO notification_jobs(user_id, workspace_id, title, body, category, scheduled_at) VALUES
                   (11, %s, 't', 'b', 'calendar', %s), (11, %s, 't', 'b', 'calendar', %s) RETURNING id""",
                (WS_A, now - timedelta(hours=service.MAX_DELIVERY_DELAY_HOURS + 1), WS_A, now - timedelta(minutes=5)))
    stale, fresh = (row[0] for row in cur.fetchall())
    assert service.send_due_notifications()["due_jobs"] == 1
    cur.execute("SELECT id, status FROM notification_jobs ORDER BY id")
    assert cur.fetchall() == [(stale, "pending"), (fresh, "failed")]  # no subscription for the fresh one


def _no_enqueue(monkeypatch):
    monkeypatch.setattr(service, "enqueue_calendar_reminders", lambda: 0)
    monkeypatch.setattr(service, "enqueue_fixed_expense_reminders", lambda: 0)
    import backend.sports.service as sports
    monkeypatch.setattr(sports, "enqueue_owner_sports_digest_notifications", lambda: {"status": "OK"})


def test_two_concurrent_cron_runs_send_each_job_once(cur, monkeypatch):
    """Two schedulers overlap: every due job is pushed exactly once, and no database
    transaction is open while a push service is being called."""
    import threading
    import time

    _no_enqueue(monkeypatch)
    now = datetime.now(timezone.utc)
    cur.execute("INSERT INTO notification_subscriptions(workspace_id) VALUES (%s)", (WS_A,))
    for i in range(12):
        cur.execute("""INSERT INTO notification_jobs(user_id, workspace_id, title, body, category, scheduled_at)
                       VALUES (11, %s, %s, 'b', 'calendar', %s)""", (WS_A, f"t{i}", now - timedelta(minutes=5)))
    pushes, open_tx = [], []
    lock = threading.Lock()
    probe = psycopg2.connect(database.DATABASE_URL)
    probe.autocommit = True

    def fake_send(_conn, _subscription, title, _body, _category):
        with probe.cursor() as c:  # nothing of the scheduler holds a transaction during the push
            c.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                      "AND state LIKE 'idle in transaction%%' AND pid <> pg_backend_pid()")
            open_tx.append(c.fetchone()[0])
        time.sleep(0.05)
        with lock:
            pushes.append(title)
        return True, None

    monkeypatch.setattr(service, "_send_to_subscription", fake_send)
    runs = [threading.Thread(target=service.send_due_notifications) for _ in range(2)]
    for run in runs:
        run.start()
    for run in runs:
        run.join()
    probe.close()
    assert sorted(pushes) == sorted(f"t{i}" for i in range(12))  # each once, none lost
    assert set(open_tx) == {0}
    cur.execute("SELECT DISTINCT status FROM notification_jobs")
    assert cur.fetchall() == [("sent",)]


def test_a_lost_claim_is_retried_after_its_lease(cur, monkeypatch):
    """A crash between claiming and recording leaves the job 'sending': it is retried
    only once the lease has passed, never while another run may still be sending it."""
    _no_enqueue(monkeypatch)
    now = datetime.now(timezone.utc)
    cur.execute("INSERT INTO notification_subscriptions(workspace_id) VALUES (%s)", (WS_A,))
    cur.execute("""INSERT INTO notification_jobs(user_id, workspace_id, title, body, category, scheduled_at, status, updated_at)
                   VALUES (11, %s, 'recent', 'b', 'calendar', %s, 'sending', NOW()),
                          (11, %s, 'lost', 'b', 'calendar', %s, 'sending', NOW() - make_interval(mins => %s))""",
                (WS_A, now - timedelta(minutes=5), WS_A, now - timedelta(minutes=5), service.CLAIM_LEASE_MINUTES + 1))
    sent = []
    monkeypatch.setattr(service, "_send_to_subscription", lambda _c, _s, title, _b, _cat: (sent.append(title), (True, None))[1])
    assert service.send_due_notifications()["due_jobs"] == 1
    assert sent == ["lost"]
    cur.execute("SELECT title, status FROM notification_jobs ORDER BY title")
    assert cur.fetchall() == [("lost", "sent"), ("recent", "sending")]
