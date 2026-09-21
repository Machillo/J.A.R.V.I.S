import pytest
from fastapi import HTTPException

from backend.user_product import gmail_consent


class _Result:
    def __init__(self, one=None): self.one = one
    def fetchone(self): return self.one


class _Connection:
    def __init__(self, results): self.results = iter(results); self.calls = []; self.committed = False
    def __enter__(self): return self
    def __exit__(self, *_args): return None
    def execute(self, query, params=()): self.calls.append((query, params)); return next(self.results)
    def commit(self): self.committed = True


def _identity(monkeypatch):
    monkeypatch.setattr(gmail_consent, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(gmail_consent, "get_current_workspace_id", lambda: "workspace-a")


def test_accepts_current_version_and_records_scope(monkeypatch):
    _identity(monkeypatch)
    connection = _Connection([_Result(), _Result({"accepted_at": "now"})])
    monkeypatch.setattr(gmail_consent, "get_connection", lambda: connection)
    result = gmail_consent.accept_gmail_consent(accepted=True, version=gmail_consent.GMAIL_CONSENT_VERSION)
    assert connection.committed is True
    assert connection.calls[0][1] == ("account-a", "workspace-a", gmail_consent.GMAIL_CONSENT_VERSION)
    assert result["required"] is False


def test_rejects_stale_or_missing_consent():
    with pytest.raises(HTTPException) as stale:
        gmail_consent.accept_gmail_consent(accepted=True, version="old")
    assert stale.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        gmail_consent.accept_gmail_consent(accepted=False, version=gmail_consent.GMAIL_CONSENT_VERSION)
    assert missing.value.status_code == 422


def test_connection_requires_consent(monkeypatch):
    monkeypatch.setattr(gmail_consent, "gmail_consent_status", lambda: {"required": True})
    with pytest.raises(HTTPException) as exc:
        gmail_consent.require_gmail_consent()
    assert exc.value.status_code == 409
