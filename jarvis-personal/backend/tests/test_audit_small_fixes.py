"""Security audit run-2 fixes: upload path, public-path exception redaction, IBKR token."""
from __future__ import annotations

import io
import logging
import os

import pytest
import requests
from fastapi import UploadFile
from fastapi.testclient import TestClient

from backend import main
from backend.importers import routes as importers
from backend.integrations import ibkr_readonly

SECRET = "DUMMYFLEXTOKEN0000"


@pytest.mark.parametrize("filename", ["../escaped.txt", "/tmp/claude-audit-abs.txt", "normal.pdf"])
def test_the_bac_upload_never_uses_the_client_filename_as_a_path(tmp_path, monkeypatch, filename):
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    seen = {}
    monkeypatch.setattr(importers, "parse_bac_credit_card_pdf", lambda path: seen.setdefault("path", path) and {"ok": True})
    importers.preview_bac_pdf(UploadFile(file=io.BytesIO(b"dummy"), filename=filename))
    assert os.path.basename(seen["path"]) != os.path.basename(filename)
    assert not os.path.exists(seen["path"])  # removed after parsing
    assert not (tmp_path / "escaped.txt").exists() and not os.path.exists("/tmp/claude-audit-abs.txt")
    assert not (workdir / "uploads").exists()


@pytest.mark.parametrize("error", [
    requests.HTTPError(f"503 Server Error for url: https://example.test/SendRequest?t={SECRET}&q=1"),
    ValueError(f"unexpected {SECRET}"),  # not handled by the route: reaches the middleware
])
def test_a_public_path_exception_never_logs_its_message(monkeypatch, caplog, error):
    monkeypatch.setenv("IBKR_FLEX_CRON_SECRET", "dummy-cron-secret")
    monkeypatch.setattr(main, "disabled_feature_for_request", lambda *a, **k: None)

    def fail():
        raise error

    monkeypatch.setattr(ibkr_readonly, "sync_flex_snapshot", fail)
    client = TestClient(main.app, raise_server_exceptions=False)
    with caplog.at_level(logging.DEBUG):
        response = client.post("/integrations/ibkr/flex/cron", headers={"X-Jarvis-Cron-Secret": "dummy-cron-secret"})
    assert response.status_code in (500, 502)
    assert SECRET not in caplog.text and SECRET not in response.text
