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
    assert elapsed < 0.2, f"/status waited {elapsed:.2f}s behind authentication"
