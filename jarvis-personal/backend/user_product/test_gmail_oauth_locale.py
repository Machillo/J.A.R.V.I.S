"""Google's consent screens follow the app's language (EN → EN, ES → ES, else EN).

The Gmail authorization URL carries Google's documented OpenID Connect ``hl``
parameter; nothing else in the request changes: the same scope (exactly
gmail.readonly), client, redirect URI, state and PKCE.
"""
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.user_product import gmail_service, mail_oauth
from backend.user_product import routes as user_product_routes
from backend.user_product.test_mail_oauth import A, GMAIL_CLIENT, _as, env  # noqa: F401

EXPECTED_KEYS = {
    "client_id", "redirect_uri", "response_type", "scope", "access_type", "prompt",
    "state", "code_challenge", "code_challenge_method", "hl",
}


@pytest.mark.parametrize(("candidates", "expected"), [
    (("en",), "en"), (("en-US",), "en"), (("en-GB",), "en"), (("EN_us",), "en"),
    (("es",), "es"), (("es-CR",), "es"), (("es-ES",), "es"), (("es-419",), "es"),
    (("fr-FR",), "en"), (("pt-BR",), "en"), (("",), "en"), ((None,), "en"), ((), "en"),
    (("es-CR,es;q=0.9,en;q=0.8",), "es"), (("en-US,en;q=0.9,es;q=0.8",), "en"),
    # The language the app sends wins over its Accept-Language, in both directions.
    (("en", "es-CR"), "en"), (("es", "en-US"), "es"),
    # An empty app value defers to the header; an unknown one is English, not the header.
    ((None, "es-CR"), "es"), (("", "es"), "es"), (("de", "es"), "en"),
    # Only en/es ever come out: nothing can be injected into the URL.
    (("en&scope=https://mail.google.com/",), "en"), (("es-CR\r\nX: y",), "es"), (("x" * 500,), "en"),
])
def test_oauth_locale_normalizes_to_english_or_spanish(candidates, expected):
    assert mail_oauth.oauth_locale(*candidates) == expected


def _query(url):
    parsed = urlparse(url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == ("https", "accounts.google.com", "/o/oauth2/v2/auth")
    query = parse_qs(parsed.query, keep_blank_values=True)
    assert all(len(values) == 1 for values in query.values()), "no duplicated parameters"
    return {key: values[0] for key, values in query.items()}


@pytest.mark.parametrize(("locale", "hl"), [("en", "en"), ("es", "es"), ("fr", "en"), ("es-419", "es")])
def test_authorization_url_adds_only_hl_and_keeps_the_security_parameters(env, locale, hl):
    query = _query(_as(A, gmail_service.begin_gmail_connection, "current_year", locale)["authorization_url"])
    assert set(query) == EXPECTED_KEYS
    assert query["hl"] == hl
    assert query["scope"] == "https://www.googleapis.com/auth/gmail.readonly"
    assert query["client_id"] == GMAIL_CLIENT[0] and query["redirect_uri"] == GMAIL_CLIENT[2]
    assert query["response_type"] == "code" and query["access_type"] == "offline"
    assert query["prompt"] == "consent select_account"
    assert query["code_challenge_method"] == "S256" and len(query["code_challenge"]) >= 43 and len(query["state"]) >= 43


def test_older_callers_without_a_locale_get_english(env):
    assert _query(_as(A, gmail_service.begin_gmail_connection)["authorization_url"])["hl"] == "en"


def test_connect_route_uses_the_app_language_then_accept_language(monkeypatch):
    user = {**A, "email": "persona@example.com"}
    monkeypatch.setattr(main, "authenticate_access_token", lambda _token, **_kwargs: user)
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(user_product_routes, "require_feature", lambda *_args, **_kwargs: None)
    received = []
    monkeypatch.setattr(user_product_routes, "begin_gmail_connection",
                        lambda scope, locale="en": received.append((scope, locale)) or {"authorization_url": "x"})
    client, auth = TestClient(main.app), {"Authorization": "Bearer t"}

    def post(body=None, language=None):
        headers = {**auth, **({"Accept-Language": language} if language else {})}
        assert client.post("/user-product/vip/gmail/connect", headers=headers, json=body).status_code == 200
        return received[-1][1]

    assert post({"import_scope": "current_year", "locale": "en-US"}, "es") == "en"  # app EN on a Spanish header
    assert post({"import_scope": "current_year", "locale": "es-CR"}, "en") == "es"  # app ES on an English header
    assert post({"import_scope": "current_year"}, "en") == "en"   # installed builds: no locale, header decides
    assert post({"import_scope": "current_year"}, "es") == "es"
    assert post() == "en"                                          # nothing known: English
    assert client.post("/user-product/vip/gmail/connect", headers=auth,
                       json={"import_scope": "current_year", "locale": "x" * 36}).status_code == 422
