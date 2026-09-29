"""The Labs database: a local, disposable PostgreSQL (embedded pgserver by default).

Nothing here accepts a remote database. Destructive operations (reset, seed)
require, in this order:
1. an active Labs process (``labs.runtime.require_active``: DINCR_ENV=labs, no
   production settings, local DSN named ``dincr_labs*``), and
2. the database itself carries the Labs marker row written when Labs created it.
A production database never has the marker, so even a DSN that slipped past the
first check is refused before anything is dropped or written.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from labs import guard

LABS_HOME = Path(os.environ.get("DINCR_LABS_HOME") or Path.home() / ".dincr-labs")
DEFAULT_DB = "dincr_labs"
MARKER_TABLE = "dincr_labs_marker"
MARKER_VALUE = "dincr-labs-local-disposable"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILES = (
    ROOT / "database" / "baseline" / "v1_identity_ownership.sql",
    Path(__file__).resolve().parent / "schema" / "labs_schema.sql",
)


def _with_database(uri: str, name: str) -> str:
    parts = urlsplit(uri)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


def start_server(data_dir: Path | None = None, cleanup_mode: str | None = "stop"):
    """Start (or reuse) the local embedded server. Called by the launcher, never by the backend."""
    import pgserver

    data_dir = Path(data_dir or LABS_HOME / "pg")
    data_dir.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(data_dir, cleanup_mode=cleanup_mode)
    return server


def admin_uri_for(server) -> str:
    uri = server.get_uri()
    guard.check_database_url(_with_database(uri, DEFAULT_DB))  # the server itself must be local
    return uri


def ensure_database(admin_uri: str, name: str = DEFAULT_DB) -> str:
    """Create the Labs database on the local server if missing; return its DSN."""
    import psycopg2

    if not name.startswith(guard.LABS_DB_PREFIX) or not name.replace("_", "").isalnum():
        raise guard.LabsRefused(f"invalid Labs database name {name!r}")
    dsn = guard.check_database_url(_with_database(admin_uri, name))
    admin = psycopg2.connect(admin_uri)
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{name}"')
    finally:
        admin.close()
    return dsn


def _connect(dsn: str):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(guard.check_database_url(dsn), cursor_factory=RealDictCursor)


def has_marker(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS t", (f"public.{MARKER_TABLE}",))
        if not cur.fetchone()["t"]:
            return False
        cur.execute(f"SELECT value FROM {MARKER_TABLE} WHERE id=1")
        row = cur.fetchone()
        return bool(row and row["value"] == MARKER_VALUE)


def _is_empty(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' AND c.relkind IN ('r','p')")
        return cur.fetchone()["n"] == 0


def verify_labs_or_empty(dsn: str) -> None:
    """Refuse a database that has tables but no Labs marker.

    A local port can be a tunnel to a hosted database (ssh -L, a proxy): its DSN
    looks local. A production database always has tables and never the marker,
    so activation stops before the backend is even imported.
    """
    conn = _connect(dsn)
    try:
        if not (has_marker(conn) or _is_empty(conn)):
            raise guard.LabsRefused("the Labs database URL leads to a database Labs did not create "
                                    "(tables without the Labs marker; a tunnel?). Labs stops here.")
    finally:
        conn.close()


def require_labs_database(conn) -> None:
    if not has_marker(conn):
        raise guard.LabsRefused("this database has no DINCR Labs marker; Labs only writes to databases it created")


def reset(dsn: str) -> None:
    """Drop everything in the Labs database and rebuild the Labs schema.

    Double protection: the caller must be an active Labs process, and the database
    must either carry the Labs marker or be completely empty (first run).
    """
    from labs import runtime

    if runtime.require_active() != dsn:
        raise guard.LabsRefused("reset may only target the active Labs database")
    conn = _connect(dsn)
    conn.autocommit = True
    try:
        if not (has_marker(conn) or _is_empty(conn)):
            raise guard.LabsRefused("refusing to reset a database that Labs did not create (no marker, not empty)")
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
            for role in ("anon", "authenticated"):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
                if not cur.fetchone():
                    cur.execute(f'CREATE ROLE "{role}" NOLOGIN')
            for path in SCHEMA_FILES:
                cur.execute(path.read_text(encoding="utf-8"))
            cur.execute(f"CREATE TABLE {MARKER_TABLE} (id INT PRIMARY KEY CHECK (id=1), value TEXT NOT NULL, "
                        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
            cur.execute(f"INSERT INTO {MARKER_TABLE}(id,value) VALUES(1,%s)", (MARKER_VALUE,))
    finally:
        conn.close()


def connect_labs(dsn: str | None = None):
    """A connection to the active Labs database, refused unless it carries the marker."""
    from labs import runtime

    active_dsn = runtime.require_active()
    if dsn is not None and dsn != active_dsn:
        raise guard.LabsRefused("only the active Labs database may be opened")
    conn = _connect(active_dsn)
    try:
        require_labs_database(conn)
    except Exception:
        conn.close()
        raise
    return conn
