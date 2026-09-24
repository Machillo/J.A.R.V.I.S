from types import SimpleNamespace

import pytest

from backend.product_ops import service


class _Result:
    def __init__(self, one=None):
        self.one = one

    def fetchone(self):
        return self.one


class _Conn:
    def __init__(self, recent):
        self.recent = recent

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, _params=()):
        if "COUNT(*) AS total" in sql:
            return _Result({"total": self.recent})
        if sql.lstrip().startswith("INSERT INTO feedback_reports"):
            return _Result({"id": 7, "category": "error", "subject": "x", "status": "new", "severity": "critical",
                            "created_at": None, "occurrence_count": 1, "affected_operations": [], "discord_alerted_at": None})
        return _Result(None)

    def commit(self):
        return None


PAYLOAD = SimpleNamespace(path="/user-product/finance/income", method="POST", status=500, screen="finance",
                          request_id="req", error_reference="ref", retry_count=0, app_version="1.9.11",
                          platform="android", error_type="http")


@pytest.mark.parametrize("recent, alerted", [(0, True), (4, True), (5, False), (40, False)])
def test_client_reported_incidents_cannot_spam_support(monkeypatch, recent, alerted):
    sent = []
    monkeypatch.setattr(service, "get_current_user", lambda: {"account_id": "account-a", "workspace_id": "workspace-a"})
    monkeypatch.setattr(service, "get_connection", lambda: _Conn(recent))
    monkeypatch.setattr(service, "ensure_schema", lambda _conn: None)
    monkeypatch.setattr(service, "_incident_fingerprint", lambda _p: "fp")
    monkeypatch.setattr(service, "_send_support_email", lambda **_k: sent.append("email") or True)
    monkeypatch.setattr(service, "_send_support_discord", lambda **_k: sent.append("discord") or True)
    monkeypatch.setattr(service, "_mark_discord_alerted", lambda _id: None)
    monkeypatch.setattr(service, "_record_event_safely", lambda *_a, **_k: None)

    result = service.create_automatic_incident(PAYLOAD)

    assert result["public_id"] == "DINCR-000007", "the incident is always recorded"
    assert (sent == ["email", "discord"]) is alerted
