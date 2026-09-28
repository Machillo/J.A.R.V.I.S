"""A Supabase Auth outage or rate limit must not sign users out.

Only Supabase's own verdict on the token (a 4xx other than 429) makes the session invalid. A 429
or a 5xx is an infrastructure failure: the backend answers 503 so the app retries,
instead of a 401 that the app treats as an expired session. Synthetic tokens only.
"""
import pytest
import requests
from fastapi import HTTPException

from backend.auth import service


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return {}


@pytest.fixture
def supabase(monkeypatch):
    monkeypatch.setattr(service, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(service, "SUPABASE_ANON_KEY", "anon")
    return lambda code: monkeypatch.setattr(service.requests, "get", lambda *a, **k: _Response(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_supabase_rejecting_the_token_is_an_invalid_session(supabase, code):
    supabase(code)
    with pytest.raises(HTTPException) as caught:
        service.verify_supabase_token("header.claims.signature")
    assert caught.value.status_code == 401


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_supabase_failing_is_retryable_not_a_sign_out(supabase, code):
    supabase(code)
    with pytest.raises(HTTPException) as caught:
        service.verify_supabase_token("header.claims.signature")
    assert caught.value.status_code == 503


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError])
def test_supabase_unreachable_is_retryable_not_a_sign_out(monkeypatch, error):
    monkeypatch.setattr(service, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(service, "SUPABASE_ANON_KEY", "anon")

    def unreachable(*_args, **_kwargs):
        raise error("synthetic")

    monkeypatch.setattr(service.requests, "get", unreachable)
    with pytest.raises(HTTPException) as caught:
        service.verify_supabase_token("header.claims.signature")
    assert caught.value.status_code == 503
