"""Activate a Labs process: guard, network block, then (and only then) the backend.

Order matters and is enforced:
1. the environment is checked (``labs.guard.check_environment``);
2. outbound networking is limited to loopback (``labs.netguard``);
3. ``backend/.env`` auto-loading is disabled: ``import backend`` normally loads it
   (without overriding), which would re-inject production settings into a
   scrubbed Labs process;
4. the backend is imported with the Labs database as ``DATABASE_URL``;
5. the database behind the URL is empty or carries the Labs marker (a local
   tunnel to production is refused here), and
6. the environment is checked again after the import, and the backend's frozen
   ``DATABASE_URL`` must equal the Labs database.

A process that imported ``backend`` before activation is refused: its settings
may already come from ``backend/.env`` or the caller's shell.
"""
from __future__ import annotations

import os
import sys

from labs import guard, netguard

_ACTIVE: dict[str, str] = {}


def _disable_backend_dotenv() -> None:
    import dotenv

    def refused(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return False  # Labs never reads backend/.env: settings come only from the scrubbed environment

    dotenv.load_dotenv = refused


def activate() -> str:
    """Make this process a Labs process; return the Labs database URL."""
    if _ACTIVE:
        return _ACTIVE["dsn"]
    already = sorted(name for name in sys.modules if name == "backend" or name.startswith("backend."))
    if already:
        raise guard.LabsRefused("the backend was imported before Labs was activated; start Labs with `python -m labs`")
    dsn = guard.check_environment()
    netguard.install()
    from labs import db

    db.verify_labs_or_empty(dsn)  # no switch turns this off
    _disable_backend_dotenv()
    os.environ["DATABASE_URL"] = dsn
    os.environ["DINCR_DB_APPLICATION_NAME"] = "dincr-labs"
    from backend.core import database  # noqa: PLC0415 (import only after the guard)

    guard.check_environment()  # nothing the import did may have added a production setting
    if database.DATABASE_URL != dsn:
        raise guard.LabsRefused("the backend database URL is not the Labs database")
    _ACTIVE["dsn"] = dsn
    return dsn


def active() -> bool:
    return bool(_ACTIVE)


def require_active() -> str:
    """Every Labs operation that touches the backend or a database calls this first."""
    if not _ACTIVE:
        raise guard.LabsRefused("Labs is not active in this process; start it with `python -m labs`")
    guard.check_environment()
    return _ACTIVE["dsn"]
