import base64
import json

import pytest
from fastapi import HTTPException

from backend.auth import service


def _token(amr):
    claims = base64.urlsafe_b64encode(json.dumps({"amr": amr}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


def _user(provider="google", **extra):
    return {"id": "11111111-1111-1111-1111-111111111111", "email": "persona@example.com",
            "app_metadata": {"provider": provider, "providers": [provider]}, **extra}


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


@pytest.fixture
def supabase(monkeypatch):
    monkeypatch.setattr(service, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(service, "SUPABASE_ANON_KEY", "anon")

    def respond(user):
        monkeypatch.setattr(service.requests, "get", lambda *a, **k: _Response(user))
    return respond


@pytest.mark.parametrize("provider", ["google", "apple"])
def test_oauth_sessions_are_accepted(supabase, provider):
    supabase(_user(provider))
    identity = service.verify_supabase_token(_token([{"method": "oauth", "timestamp": 1}]))
    assert identity["email"] == "persona@example.com"


@pytest.mark.parametrize("amr, provider", [
    ([{"method": "password", "timestamp": 1}], "email"),          # API-only password sign-up
    ([{"method": "otp", "timestamp": 1}], "email"),               # magic link / OTP
    ([{"method": "password", "timestamp": 1}], "google"),         # password identity linked to a Google user
    ([{"method": "oauth"}, {"method": "password"}], "google"),
    ([{"method": "oauth", "timestamp": 1}], "github"),            # provider DINCR never offers
    ([], "email"),                                                # no amr claim: provider decides
])
def test_non_oauth_or_unknown_provider_sessions_never_become_identities(supabase, amr, provider):
    supabase(_user(provider))
    with pytest.raises(HTTPException) as error:
        service.verify_supabase_token(_token(amr))
    assert error.value.status_code == 403


def test_oauth_with_a_second_factor_is_accepted(supabase):
    supabase(_user("google"))
    assert service.verify_supabase_token(_token([{"method": "oauth"}, {"method": "totp"}]))["email"] == "persona@example.com"


def test_anonymous_users_are_rejected(supabase):
    supabase(_user("google", is_anonymous=True))
    with pytest.raises(HTTPException):
        service.verify_supabase_token(_token([{"method": "anonymous"}]))


def test_malformed_token_claims_fall_back_to_the_provider_check(supabase):
    supabase(_user("google"))
    assert service.verify_supabase_token("not-a-jwt")["email"] == "persona@example.com"
    supabase(_user("email"))
    with pytest.raises(HTTPException):
        service.verify_supabase_token("not-a-jwt")
