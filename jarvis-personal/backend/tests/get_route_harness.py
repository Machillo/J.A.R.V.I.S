"""Calls every GET route of the app against a database that answers like an empty one and
records every write (functional protection gates, R1; read purity, CLAUDE.md §4.C).

- SELECTs return no rows, except aggregates without GROUP BY, which return one row of zeros
  (as PostgreSQL does), and schema-catalog checks, which answer that the object exists (the
  database is migrated). A brand-new account is exactly this state, so every GET must handle it.
- INSERT / UPDATE / DELETE / UPSERT / TRUNCATE / CREATE / ALTER are recorded and never run.
- Outbound network is refused, so no GET can reach a third party while the gate runs.

It cannot see writes that only happen when rows exist; those paths stay covered by the
ledger-backed tests (test_read_surfaces_are_read_only.py, finance/test_debt_reads_are_read_only.py).
"""
from __future__ import annotations

import re
import socket
import sys
from contextlib import contextmanager

AUTH = {"Authorization": "Bearer test-token"}
USERS = {
    "owner": {"id": 1, "account_id": "00000000-0000-4000-8000-0000000000a1", "workspace_id": "00000000-0000-4000-8000-00000000000a",
              "role": "owner", "email": "owner@example.test"},
    "user": {"id": 50, "account_id": "00000000-0000-4000-8000-0000000000b1", "workspace_id": "00000000-0000-4000-8000-00000000000b",
             "role": "user", "email": "user@example.test"},
}
_WRITE = re.compile(
    r"^\s*(?:WITH\b.*?\)\s*)?(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE|CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)|ALTER\s+TABLE)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?([a-z_]+)",
    re.I | re.S,
)
_AGGREGATE = re.compile(r"\b(SUM|COUNT|COALESCE|MAX|MIN|AVG)\s*\(", re.I)
_GROUP_BY = re.compile(r"GROUP\s+BY", re.I)
_CATALOG = re.compile(r"to_regclass\(|information_schema\.|pg_catalog\.|\bpg_tables\b|\bpg_class\b", re.I)


class _ZeroRow(dict):
    """The single row of an aggregate over no rows: every column reads as zero."""

    def __missing__(self, key):
        return 0

    def get(self, key, default=None):
        return dict.get(self, key, 0)


class _PresentRow(dict):
    """A schema-catalog answer on a migrated database: the object exists."""

    def __missing__(self, key):
        return "present"

    def get(self, key, default=None):
        return dict.get(self, key, "present")


class Recorder:
    def __init__(self):
        self.writes: list[tuple[str, str]] = []

    def execute(self, query: str):
        from backend.core import database

        match = _WRITE.match(query)
        if match:
            self.writes.append((match.group(1).split()[0].upper(), match.group(2).lower()))
            return database.PostgresCursorResult(rows=[], rowcount=0)
        if _CATALOG.search(query):
            return database.PostgresCursorResult(rows=[_PresentRow()], rowcount=1)
        head = re.split(r"\bFROM\b", query, maxsplit=1, flags=re.I)[0]
        if _AGGREGATE.search(head) and not _GROUP_BY.search(query):
            return database.PostgresCursorResult(rows=[_ZeroRow()], rowcount=1)
        return database.PostgresCursorResult(rows=[], rowcount=0)


def _refuse_network(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if host in ("127.0.0.1", "::1", "localhost"):
        return _ORIGINAL_CONNECT(self, address)
    raise OSError("network disabled while the GET gate runs")


_ORIGINAL_CONNECT = socket.socket.connect


@contextmanager
def harness(monkeypatch, role: str):
    """A TestClient for ``role`` over the recording database. Yields (client, recorder)."""
    from fastapi.testclient import TestClient

    from backend import main
    from backend.core import database

    recorder = Recorder()
    monkeypatch.setattr(database.PostgresConnection, "__init__", lambda self: setattr(self, "_released", False))
    monkeypatch.setattr(database.PostgresConnection, "execute", lambda self, query, params=(): recorder.execute(query))
    for name in ("commit", "rollback", "close"):
        monkeypatch.setattr(database.PostgresConnection, name, lambda self: None)
    monkeypatch.setattr(socket.socket, "connect", _refuse_network)
    # Plans are not under test here (role gates are): every plan feature is granted.
    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("backend.") and callable(getattr(module, "require_feature", None)):
            monkeypatch.setattr(module, "require_feature", lambda *_a, **_k: True)
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token: USERS[role])
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_a, **_k: None)
    yield TestClient(main.app, raise_server_exceptions=False), recorder


def get_routes() -> list[str]:
    from backend import main

    return sorted({route.path for route in main.app.routes
                   if "GET" in (getattr(route, "methods", None) or set()) and hasattr(route, "endpoint")
                   and not route.path.startswith(("/docs", "/redoc", "/openapi"))})


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "1", path)


def call_every_get(monkeypatch, role: str) -> dict[str, dict]:
    """``{path: {"status": int, "writes": [(op, table), ...]}}`` for every GET route as ``role``."""
    results = {}
    with harness(monkeypatch, role) as (client, recorder):
        for path in get_routes():
            recorder.writes.clear()
            status = client.get(concrete(path), headers=AUTH, follow_redirects=False).status_code
            results[path] = {"status": status, "writes": sorted(set(recorder.writes))}
    return results
