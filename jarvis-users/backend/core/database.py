import os
from dataclasses import dataclass
from decimal import Decimal
from threading import Lock
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_POOL_MIN = max(1, int(os.getenv("DB_POOL_MIN", "1")))
DB_POOL_MAX = max(DB_POOL_MIN, int(os.getenv("DB_POOL_MAX", "8")))

_pool: ThreadedConnectionPool | None = None
_pool_lock = Lock()


class DatabaseConfigError(RuntimeError):
    pass


@dataclass
class PostgresCursorResult:
    rows: list[dict[str, Any]]
    lastrowid: int | None = None
    rowcount: int = 0

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


def _serialize(value: Any):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _serialize(value) for key, value in dict(row).items()}


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if not DATABASE_URL:
        raise DatabaseConfigError("DATABASE_URL no está configurada.")
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    DB_POOL_MIN,
                    DB_POOL_MAX,
                    dsn=DATABASE_URL,
                    cursor_factory=RealDictCursor,
                    connect_timeout=10,
                    application_name="jarvis-users",
                )
    return _pool


class PostgresConnection:
    def __init__(self):
        self.pool = _get_pool()
        self.conn = self.pool.getconn()
        if self.conn.closed:
            self.pool.putconn(self.conn, close=True)
            self.conn = self.pool.getconn()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        self.close()

    def execute(self, query: str, params=()):
        prepared = query.strip()
        if "?" in prepared:
            raise ValueError("Usa placeholders PostgreSQL %s, no '?'.")
        if prepared.lower().startswith("insert") and " returning " not in prepared.lower():
            prepared = prepared.rstrip(";") + " RETURNING id"

        with self.conn.cursor() as cursor:
            cursor.execute(prepared, params)
            rows = []
            lastrowid = None
            if cursor.description:
                rows = [_serialize_row(row) for row in cursor.fetchall()]
                if rows and "id" in rows[0]:
                    lastrowid = rows[0]["id"]
            return PostgresCursorResult(rows=rows, lastrowid=lastrowid, rowcount=cursor.rowcount)

    def commit(self):
        self.conn.commit()

    def close(self):
        if self.conn is None:
            return
        conn = self.conn
        self.conn = None
        try:
            # Never return an open transaction to the pool.
            conn.rollback()
            self.pool.putconn(conn)
        except Exception:
            try:
                self.pool.putconn(conn, close=True)
            except Exception:
                pass


def get_connection():
    return PostgresConnection()


def init_database():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
        conn.rollback()
    finally:
        pool.putconn(conn)


def close_database():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
