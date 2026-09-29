"""Labs stays out of DINCR: nothing shipped imports it, and it never becomes a backdoor."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LABS = ROOT / "labs"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    return names


def test_no_backend_module_imports_labs():
    offenders = [str(p.relative_to(ROOT)) for p in BACKEND.rglob("*.py")
                 if any(m == "labs" or m.startswith("labs.") for m in _imports(p))]
    assert offenders == []


def test_no_backend_code_mentions_labs_activation_or_fake_identities():
    for path in BACKEND.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "DINCR_LABS" not in text and "labs.runtime" not in text, path


def test_the_frontend_and_native_apps_never_reference_labs():
    for base in (FRONTEND / "src", ROOT / "native"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix in {".js", ".jsx", ".ts", ".tsx", ".kt", ".swift"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                assert "DINCR_LABS" not in text and "/labs/" not in text, path


def test_labs_has_no_http_server_route_or_endpoint():
    """Labs is a local CLI: no FastAPI app, router or listening server that could be deployed as a backdoor."""
    for path in LABS.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"FastAPI\(|APIRouter\(|uvicorn|\.listen\(|http\.server|flask", text), path


PROVIDER_MARKERS = ("api.openai.com", "openai.azure.com", "OPENAI_API_KEY", "generativelanguage.googleapis.com",
                    "aiplatform.googleapis.com", "api.anthropic.com", "api.mistral.ai", "api.cohere", "api.groq.com")
PROVIDER_SDKS = ("openai", "anthropic", "google.genai", "google.generativeai", "vertexai", "langchain", "cohere",
                 "mistralai")


def test_labs_reaches_no_generative_ai_provider():
    for path in LABS.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert not [m for m in PROVIDER_MARKERS if m in text], path
        assert not [m for m in _imports(path) if m.split(".")[0] in PROVIDER_SDKS or m.startswith(PROVIDER_SDKS)], path


def test_the_fake_ai_provider_is_the_only_provider():
    from labs import ai

    fake = ai.provider("fake")
    assert fake.categorize("SUPER EJEMPLO").category == "Alimentación"
    assert fake.categorize("XYZ") == fake.categorize("XYZ")  # deterministic
    for name in ("openai", "gemini", "claude", "anthropic", ""):
        with pytest.raises(PermissionError):
            ai.provider(name)


def test_email_fixtures_are_synthetic():
    data = json.loads((LABS / "email_fixtures" / "bank_emails.json").read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    for case in data["cases"]:
        text = f"{case['subject']} {case['sender']} {case['body']}"
        assert not re.search(r"\b\d{13,19}\b", text), case["name"]  # no card numbers
        assert not re.search(r"CR\d{20}", text), case["name"]  # no IBAN
        emails = re.findall(r"[\w.+-]+@([\w.-]+)", text)
        allowed = ("notificacionesbaccr.com", "multimoney.com", "bncr.fi.cr")  # the bank sender addresses the parsers allow
        assert all(domain in allowed for domain in emails), case["name"]


def test_no_secret_is_committed_in_labs():
    pattern = re.compile(r"(sk-[A-Za-z0-9]{16,}|eyJ[A-Za-z0-9_-]{20,}\.|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")
    for path in LABS.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".json", ".sql", ".md"}:
            assert not pattern.search(path.read_text(encoding="utf-8")), path
