import logging
import os
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

import psycopg2
from psycopg2 import extensions
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


DATABASE_URL = os.getenv("DATABASE_URL")
# Connection label seen by database guards. Scripts and ad-hoc tools default to
# a name the financial delete guard does NOT exempt; backend/main.py (the web
# app) sets "dincr-backend". DINCR_DB_APPLICATION_NAME overrides both.
APPLICATION_NAME = os.getenv("DINCR_DB_APPLICATION_NAME", "dincr-script")


# Reuse of idle connections (see docs/operations/database-connections.md).
# DATABASE_URL points at Supavisor in transaction mode: an idle client
# connection holds no Postgres connection, so keeping a few authenticated ones
# per process only saves the TCP + TLS + SCRAM handshake of every get_connection().
# Acquisition never waits: with no idle connection a new one is opened, exactly
# as before, so nested get_connection() calls cannot exhaust a fixed pool.
# DINCR_DB_POOL_MAX_IDLE=0 turns reuse off.
POOL_MAX_IDLE = int(os.getenv("DINCR_DB_POOL_MAX_IDLE", "8"))
POOL_IDLE_SECONDS = float(os.getenv("DINCR_DB_POOL_IDLE_SECONDS", "300"))
POOL_MAX_AGE_SECONDS = float(os.getenv("DINCR_DB_POOL_MAX_AGE_SECONDS", "600"))


class _IdleConnections:
    """Per-process cache of idle, clean connections keyed by (DSN, application_name)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._idle: dict[tuple[str, str], list[tuple[object, float, float]]] = {}
        self._pid = os.getpid()
        self.stats = {"opened": 0, "reused": 0, "returned": 0, "discarded": 0, "reconnected": 0}

    def _expired(self, now: float, created: float, released: float) -> bool:
        return now - released > POOL_IDLE_SECONDS or now - created > POOL_MAX_AGE_SECONDS

    def _take_expired(self, now: float) -> list:
        """Remove every expired idle connection (caller holds the lock); close them outside it."""
        expired = []
        for key, stack in self._idle.items():
            keep = [entry for entry in stack if not self._expired(now, entry[1], entry[2])]
            expired.extend(entry[0] for entry in stack if self._expired(now, entry[1], entry[2]))
            self._idle[key] = keep
        return expired

    def _fork_guard(self) -> None:
        # A forked child must never use the parent's sockets: forget them without closing.
        if os.getpid() != self._pid:
            self._idle, self._pid = {}, os.getpid()

    def acquire(self, dsn: str, application_name: str):
        key, now = (dsn, application_name), time.monotonic()
        with self._lock:
            self._fork_guard()
            expired = self._take_expired(now)
            stack = self._idle.get(key) or []
            entry = stack.pop() if stack else None
        for raw in expired:
            self._discard(raw)
        while entry is not None:
            raw, created, _released = entry
            if not raw.closed:
                with self._lock:
                    self.stats["reused"] += 1
                return raw, created, True
            self._discard(raw)
            with self._lock:
                stack = self._idle.get(key) or []
                entry = stack.pop() if stack else None
        return self.open(dsn, application_name), time.monotonic(), False

    def open(self, dsn: str, application_name: str):
        raw = psycopg2.connect(dsn, cursor_factory=RealDictCursor, application_name=application_name,
                               keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)
        with self._lock:
            self.stats["opened"] += 1
        return raw

    def release(self, dsn: str, application_name: str, raw, created: float) -> None:
        """Keep a connection only if it is healthy and has no transaction open."""
        try:
            if not raw.closed and raw.info.transaction_status != extensions.TRANSACTION_STATUS_IDLE:
                raw.rollback()  # never hand an open transaction (or its snapshot) to the next caller
            healthy = (not raw.closed and raw.info.transaction_status == extensions.TRANSACTION_STATUS_IDLE
                       and not raw.autocommit and time.monotonic() - created <= POOL_MAX_AGE_SECONDS)
        except Exception:
            healthy = False
        expired = []
        if healthy and POOL_MAX_IDLE > 0:
            with self._lock:
                self._fork_guard()
                expired = self._take_expired(time.monotonic())
                stack = self._idle.setdefault((dsn, application_name), [])
                kept = len(stack) < POOL_MAX_IDLE
                if kept:
                    stack.append((raw, created, time.monotonic()))
                    self.stats["returned"] += 1
            for old in expired:
                self._discard(old)
            if kept:
                return
        self._discard(raw)

    def _discard(self, raw) -> None:
        with self._lock:
            self.stats["discarded"] += 1
        try:
            raw.close()
        except Exception:
            logger.debug("Closing a discarded database connection failed", exc_info=True)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {**self.stats, "idle": sum(len(stack) for stack in self._idle.values())}

    def clear(self) -> None:
        with self._lock:
            stacks, self._idle = list(self._idle.values()), {}
        for stack in stacks:
            for raw, _created, _released in stack:
                self._discard(raw)


_POOL = _IdleConnections()


def connection_pool_stats() -> dict[str, int]:
    """Process-local counters: opened, reused, returned, discarded and idle now."""
    return _POOL.snapshot()


def close_idle_connections() -> None:
    _POOL.clear()


class DatabaseConfigError(RuntimeError):
    pass


class DatabaseQueryError(RuntimeError):
    pass


def serialize_db_value(value: Any) -> Any:
    """
    Convierte tipos que psycopg2 devuelve desde PostgreSQL a valores seguros
    para FastAPI/JSON y para operaciones normales en el backend.
    """
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, list):
        return [serialize_db_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(serialize_db_value(item) for item in value)

    if isinstance(value, dict):
        return {key: serialize_db_value(item) for key, item in value.items()}

    return value


def serialize_row(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    return serialize_db_value(dict(row))


def serialize_rows(rows: Iterable[dict]) -> list[dict]:
    return [serialize_row(row) for row in rows]


class PostgresCursorResult:
    """
    Wrapper pequeño para mantener esta forma en los servicios:

        conn.execute(...).fetchone()
        conn.execute(...).fetchall()
        cursor.lastrowid
        cursor.rowcount

    La diferencia es que ahora todo es PostgreSQL nativo.
    """

    def __init__(self, rows=None, lastrowid=None, rowcount: int = 0):
        self.rows = rows or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class PostgresConnection:
    def __init__(self):
        if not DATABASE_URL:
            raise DatabaseConfigError(
                "DATABASE_URL no está configurada. J.A.R.V.I.S debe usar PostgreSQL/Supabase como única base de datos."
            )

        # application_name identifies the backend to database guards (the pooler
        # may report its own name); the reuse cache is keyed by it and the DSN.
        self._dsn, self._application_name = DATABASE_URL, APPLICATION_NAME
        self.conn, self._created, self._reused = _POOL.acquire(self._dsn, self._application_name)
        self._released = False
        self._used = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Uncommitted work is always discarded, with or without an exception, as
        # when the connection used to be closed here.
        self.close()

    def _validate_postgres_query(self, query: str) -> str:
        prepared = query.strip()

        blocked_fragments = [
            "datetime('now')",
            'datetime("now")',
            "INSERT OR IGNORE",
            "AUTOINCREMENT",
        ]

        upper_query = prepared.upper()
        for fragment in blocked_fragments:
            if fragment.upper() in upper_query:
                raise DatabaseQueryError(
                    f"SQL incompatible con PostgreSQL detectado: {fragment}. "
                    "Actualiza ese query a sintaxis PostgreSQL nativa."
                )

        if "?" in prepared:
            raise DatabaseQueryError(
                "Placeholder SQLite '?' detectado. Usa placeholders PostgreSQL/psycopg2: %s."
            )

        clean = prepared.lower()
        if clean.startswith("insert") and " returning " not in clean:
            prepared = prepared.rstrip(";") + " RETURNING id"

        return prepared

    def execute(self, query: str, params=()):
        prepared_query = self._validate_postgres_query(query)
        self._live()
        first = not self._used
        self._used = True
        try:
            return self._execute(prepared_query, params)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            # A reused connection that died while idle (pooler restart, network)
            # fails on its first statement, before anything ran in this
            # transaction: replace it once and run that statement again.
            if not (first and self._reused and self.conn.closed):
                raise
            logger.info("Replaced a pooled database connection that closed while idle")
            dead, self.conn = self.conn, None
            _POOL._discard(dead)
            with _POOL._lock:
                _POOL.stats["reconnected"] += 1
            self.conn = _POOL.open(self._dsn, self._application_name)
            self._created, self._reused = time.monotonic(), False
            return self._execute(prepared_query, params)

    def _live(self):
        if self._released or self.conn is None:
            # The connection went back to the shared cache: it may already be running
            # another request's transaction, so using it here must fail loudly.
            raise psycopg2.InterfaceError("connection already released")
        return self.conn

    def _execute(self, prepared_query: str, params):
        with self._live().cursor() as cursor:
            cursor.execute(prepared_query, params)

            rows = []
            lastrowid = None

            if cursor.description:
                rows = serialize_rows(cursor.fetchall())
                if rows and isinstance(rows[0], dict) and "id" in rows[0]:
                    lastrowid = rows[0]["id"]

            return PostgresCursorResult(
                rows=rows,
                lastrowid=lastrowid,
                rowcount=cursor.rowcount,
            )

    def commit(self):
        self._live().commit()

    def rollback(self):
        self._live().rollback()

    def close(self):
        if self._released:
            return
        self._released = True
        raw, self.conn = self.conn, None
        if raw is not None:
            _POOL.release(self._dsn, self._application_name, raw, self._created)


def get_connection():
    return PostgresConnection()


def init_database():
    """
    En producción el schema se ejecuta desde Supabase SQL Editor usando database/schema.sql.
    Esta función queda para que main.py pueda llamarla sin crear tablas automáticamente.
    """
    if not DATABASE_URL:
        raise DatabaseConfigError(
            "DATABASE_URL no está configurada. Configúrala en Render antes de iniciar el backend."
        )
    return None
