"""Local PostgreSQL for the Labs tests (embedded pgserver; never a remote server)."""
from __future__ import annotations

import os
import uuid

import pytest

from labs import db


@pytest.fixture(scope="session")
def admin_uri(tmp_path_factory):
    try:
        import pgserver  # noqa: F401
    except ImportError:
        if os.getenv("DINCR_REQUIRE_PG_TESTS") == "1":
            pytest.fail("pgserver is required for the Labs database tests")
        pytest.skip("pgserver not installed")
    server = db.start_server(tmp_path_factory.mktemp("labs-pg"), cleanup_mode="delete")
    yield db.admin_uri_for(server)


@pytest.fixture
def labs_dsn(admin_uri):
    """A fresh, empty Labs database (activation accepts empty or marked databases only)."""
    return db.ensure_database(admin_uri, f"dincr_labs_t{uuid.uuid4().hex[:10]}")
