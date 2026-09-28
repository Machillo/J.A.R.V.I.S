"""Shared test isolation for the backend suite."""
import pytest

from backend.core import database


@pytest.fixture(autouse=True)
def _no_connection_leaks_between_tests():
    """PostgreSQL tests point the connection cache at databases they later drop: start and end clean."""
    database.close_idle_connections()
    yield
    database.close_idle_connections()
