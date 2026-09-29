"""Failure simulation for Labs: small, explicit context managers.

Each one changes behaviour only inside its ``with`` block and only in an active
Labs process. They exist to see what DINCR's code and screens do when a
dependency fails, not to test infrastructure.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any
from unittest import mock

from labs import runtime

UNREACHABLE_DSN = "postgresql://labs@127.0.0.1:1/dincr_labs_unreachable"  # loopback, closed port


@contextmanager
def db_unavailable():
    """Every backend connection fails as if the database were down."""
    runtime.require_active()
    from backend.core import database

    database.close_idle_connections()
    with mock.patch.object(database, "DATABASE_URL", UNREACHABLE_DSN):
        try:
            yield
        finally:
            database.close_idle_connections()


class FakeResponse:
    def __init__(self, status_code: int, body: str, headers: dict[str, str] | None = None):
        self.status_code, self.text, self.headers = status_code, body, headers or {"content-type": "application/json"}
        self.content = body.encode("utf-8")
        self.ok = 200 <= status_code < 400

    def json(self) -> Any:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if not self.ok:
            import requests

            raise requests.HTTPError(f"{self.status_code} (Labs simulated)", response=self)


@contextmanager
def http(status: int = 500, body: str = '{"error":"simulated"}', delay: float = 0.0):
    """Every `requests` call returns this response (after `delay` seconds); nothing leaves the machine."""
    runtime.require_active()
    import requests

    def fake(*_args, **_kwargs):
        if delay:
            time.sleep(delay)
        return FakeResponse(status, body)

    with mock.patch.object(requests, "request", fake), mock.patch.object(requests.Session, "request", lambda self, *a, **k: fake()), \
            mock.patch.object(requests, "get", fake), mock.patch.object(requests, "post", fake):
        yield


def backend_500():
    return http(500)


def malformed_response():
    return http(200, "<html>not json")


def oauth_failure():
    return http(400, '{"error":"invalid_grant","error_description":"Labs simulated"}')


@contextmanager
def timeout(seconds: float = 0.0):
    """Every `requests` call raises a timeout (after an optional delay)."""
    runtime.require_active()
    import requests

    def fake(*_args, **_kwargs):
        if seconds:
            time.sleep(seconds)
        raise requests.Timeout("Labs simulated timeout")

    with mock.patch.object(requests, "request", fake), mock.patch.object(requests.Session, "request", lambda self, *a, **k: fake()), \
            mock.patch.object(requests, "get", fake), mock.patch.object(requests, "post", fake):
        yield


def slow_network(seconds: float = 2.0):
    return http(200, "{}", delay=seconds)


@contextmanager
def parser_failure():
    """DINCR's bank parser raises on every message."""
    runtime.require_active()
    from backend.email_monitor import parser

    def broken(*_args, **_kwargs):
        raise ValueError("Labs simulated parser failure")

    with mock.patch.object(parser, "parse_financial_email", broken):
        yield


@contextmanager
def billing_verification_failure():
    """Store verification fails for Apple and Google alike."""
    runtime.require_active()
    from fastapi import HTTPException

    from backend.product_ops import store_verification

    def refused(*_args, **_kwargs):
        raise HTTPException(status_code=502, detail="Labs simulated store verification failure")

    with mock.patch.object(store_verification, "verify_apple_transaction", refused), \
            mock.patch.object(store_verification, "verify_google_purchase", refused):
        yield


def offline():
    """No network and no database: the process behaves as if the device were offline."""
    return _stack(db_unavailable(), timeout())


@contextmanager
def _stack(*managers):
    from contextlib import ExitStack

    with ExitStack() as stack:
        for manager in managers:
            stack.enter_context(manager)
        yield


KINDS = {
    "db_unavailable": db_unavailable, "backend_500": backend_500, "timeout": timeout, "slow_network": slow_network,
    "malformed_response": malformed_response, "oauth_failure": oauth_failure, "parser_failure": parser_failure,
    "billing_verification_failure": billing_verification_failure, "offline": offline,
}
