"""SEC-12: a technical cap on writes per account (core/write_limit.py, auth_middleware).

Past the cap a write is answered 429 with Retry-After before any route runs. Reads, the Owner,
other accounts and deleting the account are never held back. Synthetic identities only.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend import main
from backend.core import write_limit
from backend.core.write_limit import WriteLimiter

USER_A = {"id": "user-a", "account_id": "account-a", "workspace_id": "workspace-a", "role": "user", "plan": "free"}
USER_B = {**USER_A, "id": "user-b", "account_id": "account-b", "workspace_id": "workspace-b"}
OWNER = {**USER_A, "id": "owner", "account_id": "account-owner", "role": "owner"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def app(monkeypatch):
    """The real middleware with a cap of 3 writes per 60 s; authentication is faked by token."""
    users = {"a": USER_A, "b": USER_B, "owner": OWNER}
    monkeypatch.setattr(main, "authenticate_access_token", lambda token, **_kw: users[token])
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_args: None)
    monkeypatch.setattr(write_limit, "limiter", WriteLimiter(limit=3, window=60))

    def call(*requests):
        async def scenario():
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return [await client.request(method, path, headers={"Authorization": f"Bearer {who}", **headers})
                        for method, path, who, headers in requests]
        return asyncio.run(scenario())
    return call


# A path no route serves: an allowed request ends in 404 without touching any data.
NOWHERE = "/user-product/sec-12-nowhere"


def test_past_the_cap_a_write_is_429_with_retry_after_before_any_route(app):
    responses = app(*[("POST", NOWHERE, "a", {})] * 4)
    assert [r.status_code for r in responses] == [404, 404, 404, 429]
    refused = responses[-1]
    assert refused.json()["code"] == "too_many_writes"
    assert "cambios seguidos" in refused.json()["detail"]
    assert 1 <= int(refused.headers["Retry-After"]) <= 60
    assert refused.headers["X-Request-ID"]


def test_every_write_method_counts(app):
    responses = app(("POST", NOWHERE, "a", {}), ("PUT", NOWHERE, "a", {}), ("PATCH", NOWHERE, "a", {}),
                    ("DELETE", NOWHERE, "a", {}))
    assert [r.status_code for r in responses][-1] == 429


def test_the_message_follows_the_language(app):
    responses = app(*[("POST", NOWHERE, "a", {"Accept-Language": "en"})] * 4)
    assert responses[-1].json()["detail"].startswith("You made many changes")


def test_reads_are_never_held_back(app):
    responses = app(*[("POST", NOWHERE, "a", {})] * 3, *[("GET", NOWHERE, "a", {})] * 5)
    assert all(r.status_code == 404 for r in responses)


def test_another_account_has_its_own_window(app):
    responses = app(*[("POST", NOWHERE, "a", {})] * 4, ("POST", NOWHERE, "b", {}))
    assert [r.status_code for r in responses][-2:] == [429, 404]


def test_the_owner_is_not_held_back(app):
    responses = app(*[("POST", NOWHERE, "owner", {})] * 6)
    assert {r.status_code for r in responses} == {404}


def test_deleting_the_account_is_always_reachable(monkeypatch):
    monkeypatch.setattr(write_limit, "limiter", WriteLimiter(limit=1, window=60))
    assert write_limit.retry_after_for(USER_A, "POST", NOWHERE) is None
    assert write_limit.retry_after_for(USER_A, "POST", NOWHERE) is not None
    assert write_limit.retry_after_for(USER_A, "DELETE", "/auth/me") is None


def test_the_window_slides():
    clock = Clock()
    limiter = WriteLimiter(limit=2, window=60, clock=clock)
    assert limiter.check("a") is None
    clock.now += 30
    assert limiter.check("a") is None
    assert limiter.check("a") == pytest.approx(30.0), "the oldest write leaves the window in 30 s"
    clock.now += 30
    assert limiter.check("a") is None, "the first write left the window"
    assert limiter.check("a") is not None


def test_a_refused_write_does_not_extend_the_wait():
    clock = Clock()
    limiter = WriteLimiter(limit=1, window=60, clock=clock)
    limiter.check("a")
    for _ in range(50):
        limiter.check("a")
    clock.now += 60
    assert limiter.check("a") is None


def test_memory_is_bounded():
    limiter = WriteLimiter(limit=1, window=60, max_accounts=3, clock=Clock())
    for account in ("a", "b", "c", "d"):
        limiter.check(account)
    assert list(limiter._hits) == ["b", "c", "d"], "the account seen least recently is forgotten"
