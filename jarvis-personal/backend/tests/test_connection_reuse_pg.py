"""Idle connection reuse (backend/core/database.py) on a real PostgreSQL.

Skipped when the embedded server (pgserver) is not installed.
"""
from __future__ import annotations

import os
import threading
import time

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg2 = pytest.importorskip("psycopg2")

from backend.core import database  # noqa: E402


@pytest.fixture
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(str(os.environ.get("DINCR_PGSERVER_DIR") or tmp_path / "pg"), cleanup_mode="stop")
    admin = psycopg2.connect(server.get_uri())
    admin.autocommit = True
    name = f"reuse_{os.getpid()}_{abs(hash(str(tmp_path))) % 10**8}"
    with admin.cursor() as c:
        c.execute(f"CREATE DATABASE {name}")
    uri = server.get_uri(name)
    monkeypatch.setattr(database, "DATABASE_URL", uri)
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-backend")
    monkeypatch.setattr(database, "_POOL", database._IdleConnections())
    with database.get_connection() as conn:
        conn.execute("CREATE TABLE marks (id BIGSERIAL PRIMARY KEY, note TEXT)")
        conn.commit()
    yield {"admin": admin, "uri": uri, "name": name}
    database._POOL.clear()
    with admin.cursor() as c:
        c.execute(f"DROP DATABASE {name} WITH (FORCE)")
    admin.close()


def _pid(conn):
    return conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]


def test_a_released_connection_is_reused_instead_of_reopened(db):
    with database.get_connection() as first:
        pid = _pid(first)
    with database.get_connection() as second:
        assert _pid(second) == pid
    stats = database.connection_pool_stats()
    assert stats["reused"] >= 1 and stats["idle"] == 1


def test_uncommitted_work_and_local_settings_never_reach_the_next_caller(db):
    with database.get_connection() as conn:
        conn.execute("INSERT INTO marks(note) VALUES ('not committed')")
        conn.execute("SELECT set_config('dincr.delete_workspace', 'none', true)")
    with database.get_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM marks").fetchone()["n"] == 0
        assert conn.execute("SELECT current_setting('dincr.delete_workspace', true) AS v").fetchone()["v"] in (None, "")
        assert conn.conn.info.transaction_status == psycopg2.extensions.TRANSACTION_STATUS_INTRANS


def test_an_exception_rolls_back_and_the_connection_stays_usable(db):
    with pytest.raises(RuntimeError):
        with database.get_connection() as conn:
            conn.execute("INSERT INTO marks(note) VALUES ('rolled back')")
            raise RuntimeError("boom")
    with database.get_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM marks").fetchone()["n"] == 0


def test_a_failed_statement_leaves_no_aborted_transaction_behind(db):
    with pytest.raises(psycopg2.Error):
        with database.get_connection() as conn:
            conn.execute("SELECT 1/0")
    with database.get_connection() as conn:
        assert conn.execute("SELECT 1 AS one").fetchone()["one"] == 1


def test_a_connection_that_died_while_idle_is_replaced_transparently(db):
    with database.get_connection() as conn:
        pid = _pid(conn)
    with db["admin"].cursor() as c:
        c.execute("SELECT pg_terminate_backend(%s)", (pid,))
    time.sleep(0.2)
    with database.get_connection() as conn:
        assert _pid(conn) != pid  # the first statement ran on a fresh connection
    assert database.connection_pool_stats()["discarded"] >= 1


def test_a_failure_after_the_first_statement_is_never_retried(db):
    with database.get_connection() as conn:
        pid = _pid(conn)
        with db["admin"].cursor() as c:
            c.execute("SELECT pg_terminate_backend(%s)", (pid,))
        time.sleep(0.2)
        with pytest.raises((psycopg2.OperationalError, psycopg2.InterfaceError)):
            conn.execute("INSERT INTO marks(note) VALUES ('after the connection died')")
    with database.get_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM marks").fetchone()["n"] == 0


def test_idle_and_old_connections_are_not_reused(db, monkeypatch):
    with database.get_connection() as conn:
        pid = _pid(conn)
    monkeypatch.setattr(database, "POOL_IDLE_SECONDS", 0.0)
    with database.get_connection() as conn:
        assert _pid(conn) != pid


def test_connections_are_kept_apart_by_application_name(db, monkeypatch):
    """The #245 delete guard trusts application_name: a script must never get the backend's connection."""
    with database.get_connection() as conn:
        backend_pid = _pid(conn)
    monkeypatch.setattr(database, "APPLICATION_NAME", "dincr-script")
    with database.get_connection() as conn:
        assert _pid(conn) != backend_pid
        assert conn.execute("SELECT current_setting('application_name') AS a").fetchone()["a"] == "dincr-script"


def test_concurrent_callers_never_share_a_connection_and_idle_stays_bounded(db, monkeypatch):
    monkeypatch.setattr(database, "POOL_MAX_IDLE", 3)
    barrier, held, errors = threading.Barrier(12), [], []

    def work():
        try:
            with database.get_connection() as conn:
                barrier.wait()
                held.append(_pid(conn))
                barrier.wait()
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and len(set(held)) == 12
    assert database.connection_pool_stats()["idle"] == 3


def test_a_released_connection_cannot_be_used_again(db):
    """After its block ends the connection may already run another request's transaction."""
    with database.get_connection() as conn:
        conn.execute("SELECT 1 AS one")
    for late in (lambda: conn.execute("SELECT 1"), conn.commit, conn.rollback):
        with pytest.raises(psycopg2.InterfaceError, match="released"):
            late()


def test_expired_idle_connections_are_closed_even_under_a_fresh_one(db, monkeypatch):
    held = [database.get_connection() for _ in range(3)]
    pids = [_pid(conn) for conn in held]
    for conn in held:
        conn.close()
    assert database.connection_pool_stats()["idle"] == 3
    monkeypatch.setattr(database, "POOL_IDLE_SECONDS", 0.0)
    with database.get_connection() as conn:
        assert _pid(conn) not in pids
    assert database.connection_pool_stats()["idle"] == 1  # the three stale ones were swept, not left under it
    with db["admin"].cursor() as c:
        c.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = ANY(%s)", (pids,))
        assert c.fetchone()[0] == 0


def test_reuse_can_be_turned_off(db, monkeypatch):
    monkeypatch.setattr(database, "POOL_MAX_IDLE", 0)
    with database.get_connection() as conn:
        pid = _pid(conn)
    with database.get_connection() as conn:
        assert _pid(conn) != pid
    assert database.connection_pool_stats()["idle"] == 0
