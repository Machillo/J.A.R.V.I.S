"""Technical limits on public and costly paths."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.auth import owner_bridge, routes, service
from backend.main import MAX_PUBLIC_BODY_BYTES, app


def test_an_oversized_public_body_is_refused_before_any_work():
    client = TestClient(app, raise_server_exceptions=False)
    answer = client.post("/status", content=b"x" * (MAX_PUBLIC_BODY_BYTES + 1))
    assert answer.status_code == 413


def test_junk_never_reaches_supabase(monkeypatch):
    monkeypatch.setattr(service.requests, "get", lambda *a, **k: pytest.fail("called Supabase"))
    client = TestClient(app, raise_server_exceptions=False)
    for junk in ("junk", "a.b", "a.b.c d"):
        answer = client.get("/auth/me", headers={"Authorization": f"Bearer {junk}"})
        assert answer.status_code == 401


def test_a_non_ascii_owner_token_is_401_not_500(monkeypatch):
    monkeypatch.setattr(owner_bridge, "BRIDGE_API_KEY", "synthetic")
    with pytest.raises(HTTPException) as refused:
        owner_bridge.authenticate_owner_bridge_token("ñ.ñ")
    assert refused.value.status_code == 401


def test_exports_are_limited_per_account(monkeypatch):
    monkeypatch.setattr(routes, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(routes, "export_current_account_data", lambda: {"ok": True})
    routes._export_limiter.clear()
    for _ in range(routes._export_limiter.limit):
        assert routes.export_my_data() == {"ok": True}
    with pytest.raises(HTTPException) as refused:
        routes.export_my_data()
    assert refused.value.status_code == 429
    monkeypatch.setattr(routes, "get_current_account_id", lambda: "account-b")
    assert routes.export_my_data() == {"ok": True}
    routes._export_limiter.clear()


def test_a_new_line_in_the_subject_does_not_break_the_support_email(monkeypatch):
    from backend.product_ops import service as ops

    sent = []

    class Smtp:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def starttls(self, *args, **kwargs): pass
        def login(self, *args): pass
        def send_message(self, message, *args, **kwargs): sent.append(message["Subject"])

    monkeypatch.setattr(ops.smtplib, "SMTP_SSL", Smtp)
    monkeypatch.setenv("SUPPORT_SMTP_USER", "a@example.test")
    monkeypatch.setenv("SUPPORT_SMTP_APP_PASSWORD", "synthetic")
    payload = SimpleNamespace(category="bug", subject="línea\nBcc: x@example.test", message="texto", app_version=None, screen=None, error_reference=None)
    assert ops._send_support_email(public_id="R1", email="a@example.test", plan="free", payload=payload)
    assert sent == ["[R1] BUG: línea Bcc: x@example.test"]
