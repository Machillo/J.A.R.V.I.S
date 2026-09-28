"""A workspace without an active chat session gets one (the INSERT branch)."""
from __future__ import annotations

from backend.ai import chat_memory


class _Result:
    def __init__(self, row=None, lastrowid=None):
        self.row, self.lastrowid = row, lastrowid

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        if query.lstrip().startswith("SELECT"):
            return _Result(None)  # no active session yet
        return _Result(lastrowid=7)

    def commit(self):
        pass


def test_a_new_session_is_inserted_for_the_workspace_only(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(chat_memory, "get_connection", lambda: connection)
    monkeypatch.setattr(chat_memory, "get_current_workspace_id", lambda: "workspace-a")
    assert chat_memory.get_or_create_chat_session() == 7
    query, params = connection.calls[-1]
    assert query.startswith("INSERT INTO chat_sessions") and "user_id" not in query
    assert params == ("workspace-a",)  # a 1-tuple: a bare string would be split per character
    assert query.count("%s") == len(params)
