from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.auth import legal


class _Conn:
    def __init__(self, accepted=False):
        self.accepted = accepted
        self.inserts = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, params=()):
        if sql.lstrip().startswith("INSERT INTO legal_acceptances"):
            self.inserts.append(params)
            self.insert_sql = sql
            self.accepted = True
        rows = [{"terms_accepted_at": "2026-09-24", "privacy_accepted_at": "2026-09-24"}] if self.accepted and "FROM legal_acceptances" in sql else []
        return SimpleNamespace(fetchone=lambda: rows[0] if rows else None)

    def commit(self):
        return None


def _payload(**overrides):
    return SimpleNamespace(**{"accept_terms": True, "accept_privacy": True,
                              "terms_version": legal.TERMS_VERSION, "privacy_version": legal.PRIVACY_VERSION, **overrides})


def _request(ip="203.0.113.7"):
    return SimpleNamespace(headers={"x-forwarded-for": f"{ip}, 10.0.0.1", "user-agent": "DINCR/1.9.11"}, client=None)


@pytest.fixture
def conn(monkeypatch):
    connection = _Conn()
    monkeypatch.setattr(legal, "get_connection", lambda: connection)
    monkeypatch.setattr(legal, "get_current_account_id", lambda: "account-a")
    return connection


@pytest.mark.parametrize("override", [{"accept_terms": False}, {"accept_privacy": False}])
def test_both_documents_must_be_accepted(conn, override):
    with pytest.raises(HTTPException) as error:
        legal.accept_legal_documents(_payload(**override), _request())
    assert error.value.status_code == 422 and conn.inserts == []


@pytest.mark.parametrize("override", [{"terms_version": "2026-01-01-v1"}, {"privacy_version": "old"}])
def test_a_stale_version_cannot_be_accepted(conn, override):
    with pytest.raises(HTTPException) as error:
        legal.accept_legal_documents(_payload(**override), _request())
    assert error.value.status_code == 409 and conn.inserts == []


def test_acceptance_records_current_versions_client_ip_and_is_idempotent(conn):
    result = legal.accept_legal_documents(_payload(), _request())
    assert result["status"] == "accepted" and result["required"] is False
    account_id, terms, privacy, ip, agent = conn.inserts[0]
    assert (account_id, terms, privacy) == ("account-a", legal.TERMS_VERSION, legal.PRIVACY_VERSION)
    assert ip == "203.0.113.7", "first X-Forwarded-For hop is the client"
    assert agent == "DINCR/1.9.11"
    # Re-accepting relies on the unique key: no duplicate evidence rows.
    assert "ON CONFLICT(account_id,terms_version,privacy_version) DO NOTHING" in conn.insert_sql


def test_status_requires_acceptance_until_the_current_version_is_accepted():
    assert legal.legal_status(_Conn(accepted=False), "account-a")["required"] is True
    assert legal.legal_status(_Conn(accepted=True), "account-a")["required"] is False
