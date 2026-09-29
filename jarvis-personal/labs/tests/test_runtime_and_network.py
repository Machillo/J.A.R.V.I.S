"""Activation order, backend/.env neutralization and the loopback-only network guard."""
from __future__ import annotations

import pytest

from labs import netguard
from labs.tests import adversarial
from labs.tests.helpers import run_child

LOCAL = adversarial.LOCAL_DSN  # for refusals that happen before any connection


def test_activation_blocks_the_network_and_backend_dotenv(labs_dsn):
    result = run_child("""
        import json, socket
        from labs import runtime, netguard
        runtime.activate()
        import dotenv, backend.core.env as env
        out = {"net": netguard.installed(), "dotenv_refused": env.load_dotenv("anything") is False}
        for host in ("example.com", "203.0.113.10", "db.abcdefghijkl.supabase.co"):
            try:
                socket.create_connection((host, 443), timeout=1); out[host] = "connected"
            except ConnectionError as exc:
                out[host] = type(exc).__name__
        try:
            socket.getaddrinfo("api.dincr.com", 443); out["dns"] = "resolved"
        except ConnectionError as exc:
            out["dns"] = type(exc).__name__
        import requests
        try:
            requests.get("https://oauth2.googleapis.com/token", timeout=2); out["requests"] = "sent"
        except Exception as exc:
            out["requests"] = type(exc).__name__
        import smtplib
        try:
            smtplib.SMTP("smtp.example.com", 587, timeout=2); out["smtp"] = "connected"
        except Exception as exc:
            out["smtp"] = type(exc).__name__
        print(json.dumps(out))
    """, labs_dsn)
    assert result["net"] and result["dotenv_refused"]
    assert all(result[h] == "NetworkBlocked" for h in ("example.com", "203.0.113.10", "db.abcdefghijkl.supabase.co"))
    assert result["dns"] == "NetworkBlocked"
    assert result["requests"] == "ConnectionError"  # requests wraps the NetworkBlocked refusal
    assert result["smtp"] == "NetworkBlocked"


def test_loopback_stays_reachable(labs_dsn):
    result = run_child("""
        import json, socket, threading
        from labs import runtime
        runtime.activate()
        server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1)
        port = server.getsockname()[1]
        threading.Thread(target=lambda: server.accept(), daemon=True).start()
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        print(json.dumps({"ok": True}))
    """, labs_dsn)
    assert result["ok"]


def test_activation_refuses_a_process_that_already_imported_the_backend():
    result = run_child("""
        import json
        import backend.core.env
        from labs import runtime, guard
        try:
            runtime.activate(); print(json.dumps({"refused": False}))
        except guard.LabsRefused:
            print(json.dumps({"refused": True}))
    """, LOCAL)
    assert result["refused"]


@pytest.mark.parametrize("extra, why", [
    ({"DINCR_ENV": "production"}, "not labs"),
    ({"SUPABASE_URL": "https://abcdefghijkl.supabase.co"}, "production Supabase"),
    ({"DINCR_LABS_DATABASE_URL": "postgresql://u:p@db.abcdefghijkl.supabase.co/dincr_labs"}, "production DB"),
    ({"RENDER": "true"}, "production backend"),
])
def test_a_child_with_production_settings_never_imports_the_backend(extra, why):
    result = run_child("""
        import json, sys
        from labs import runtime, guard
        try:
            runtime.activate(); refused = False
        except guard.LabsRefused:
            refused = True
        print(json.dumps({"refused": refused, "backend_loaded": any(m.startswith("backend") for m in sys.modules)}))
    """, LOCAL, extra_env=extra)
    assert result == {"refused": True, "backend_loaded": False}, why


def test_operations_refuse_when_labs_is_not_active():
    from labs import guard, runtime

    assert not runtime.active()
    with pytest.raises(guard.LabsRefused):
        runtime.require_active()


def test_netguard_address_check_is_loopback_only():
    for host in ("127.0.0.1", "::1", "localhost", "127.8.9.10"):
        netguard._check_address((host, 5432))
    for host in ("10.0.0.1", "192.168.1.1", "203.0.113.10", "example.com", "0.0.0.0", "", None):
        with pytest.raises(netguard.NetworkBlocked):
            netguard._check_address((host, 443))
