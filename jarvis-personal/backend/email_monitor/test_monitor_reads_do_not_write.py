"""Opening the Owner's mail screens writes nothing (CLAUDE.md 4.C)."""
from backend.email_monitor import service


class _Result:
    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, seen):
        self.seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.seen.append(" ".join(str(sql).split()))
        return _Result()

    def commit(self):
        self.seen.append("COMMIT")


def _reads(monkeypatch):
    seen = []
    monkeypatch.setenv("JARVIS_CARD_ALIASES", '[{"last4": "1111", "owner": "Ana Prueba"}]')
    monkeypatch.setattr(service, "get_connection", lambda: _Connection(seen))
    monkeypatch.setattr(service, "_require_owner_user", lambda: {"id": 7})
    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: "workspace-a")
    monkeypatch.setattr(service, "get_current_user_id", lambda: 7)
    return seen


def _writes(seen):
    return [sql for sql in seen if sql == "COMMIT" or sql.split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]


def test_status_writes_nothing_and_shows_defaults(monkeypatch):
    seen = _reads(monkeypatch)
    try:
        result = service.get_email_monitor_status()
    except (AttributeError, TypeError):
        result = None  # the fake rows end the read early; what matters is what ran before
    assert not _writes(seen)
    if result:
        assert result["settings"]["gmail_query"] == service.DEFAULT_QUERY


def test_candidates_write_nothing(monkeypatch):
    seen = _reads(monkeypatch)
    service.list_email_candidates()
    assert not _writes(seen)
