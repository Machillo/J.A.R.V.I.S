"""Shared test isolation for the backend suite."""
import pytest

from backend.core import database, write_limit


@pytest.fixture(autouse=True)
def _no_connection_leaks_between_tests():
    """PostgreSQL tests point the connection cache at databases they later drop: start and end clean."""
    database.close_idle_connections()
    yield
    database.close_idle_connections()


@pytest.fixture(autouse=True)
def _fresh_write_limit():
    """The SEC-12 write window is per process: each test starts with none of the earlier writes."""
    write_limit.limiter.clear()
    yield
