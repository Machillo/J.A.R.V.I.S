"""Financial answers are never kept by a client or proxy cache."""
from fastapi.testclient import TestClient

from backend.main import app


def test_every_answer_says_no_store():
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/status").headers.get("cache-control") == "no-store"
    # An early answer of the auth middleware is covered too.
    assert client.get("/auth/me").headers.get("cache-control") == "no-store"
