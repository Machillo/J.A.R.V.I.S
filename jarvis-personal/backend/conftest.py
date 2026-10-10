"""Shared test isolation for the backend suite."""
import pytest

from backend.core import database


@pytest.fixture(autouse=True)
def _no_connection_leaks_between_tests():
    """PostgreSQL tests point the connection cache at databases they later drop: start and end clean."""
    database.close_idle_connections()
    yield
    database.close_idle_connections()


def pytest_configure(config):
    config.addinivalue_line("markers", "legal_gate: run the real SEC-01 legal acceptance check (backend/auth/legal.py)")


@pytest.fixture(autouse=True)
def _accounts_have_accepted_the_current_terms(request, monkeypatch):
    """Tests that exercise other contracts through the app act as accounts that already accepted.

    The acceptance gate itself (SEC-01) is tested with `@pytest.mark.legal_gate`, which runs the
    real check against PostgreSQL (backend/tests/test_legal_acceptance_gate_pg.py).
    """
    from backend.auth import legal

    legal.forget_acceptances()
    if request.node.get_closest_marker("legal_gate") is None:
        monkeypatch.setattr(legal, "_has_accepted", lambda account_id: True)
    yield
    legal.forget_acceptances()
