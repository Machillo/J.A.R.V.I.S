"""Authentication never runs on the event loop.

auth_middleware used to call the synchronous Supabase check (an HTTP request) and
database work directly inside the async middleware, so one slow or junk request
froze every other request of the process, public ones included.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from backend import main


def test_a_slow_authentication_does_not_stall_other_requests(monkeypatch):
    def slow_rejection(token, **_kwargs):
        time.sleep(0.4)  # a slow Supabase round trip, synchronous like the real one
        raise main.HTTPException(status_code=401, detail="Token de Supabase inválido o expirado.")

    monkeypatch.setattr(main, "authenticate_access_token", slow_rejection)

    async def scenario():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            junk = [asyncio.create_task(client.get("/user-product/finance/summary", headers={"Authorization": "Bearer junk"}))
                    for _ in range(6)]
            status = await client.get("/status")  # queued behind six slow authentications
            elapsed = time.perf_counter() - started
            results = await asyncio.gather(*junk)
        return status.status_code, elapsed, [r.status_code for r in results]

    status_code, elapsed, junk_codes = asyncio.run(scenario())
    assert status_code == 200 and set(junk_codes) == {401}
    # Before the fix /status waited ~2.4 s (six 0.4 s authentications in a row).
    assert elapsed < 1.0, f"/status waited {elapsed:.2f}s behind authentication"


def test_an_infrastructure_failure_during_authentication_is_503_not_401(monkeypatch):
    """A 401 makes the app sign the user out; a database outage must not do that."""
    def database_down(token, **_kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main, "authenticate_access_token", database_down)

    async def call():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/user-product/finance/summary", headers={"Authorization": "Bearer x"})

    response = asyncio.run(call())
    assert response.status_code == 503
