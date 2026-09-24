import ast
import json
from pathlib import Path

import pytest

from backend.parser_discovery import PENDING
from backend.parser_discovery import proposal as discovery
from backend.parser_discovery.sanitize import residual_risks, sanitize_sample
from backend.scripts import propose_parser

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = (
    "Hola MARIA PRUEBA:\nBanco Ejemplo le informa una compra en COMERCIO UNO\n"
    "Monto: CRC 15.000,00\nFecha: 22/09/2026\nReferencia: 123456789012\n"
    "Contacto: maria.prueba@example.com https://banco.example/x?id=4455"
)


def test_sanitizer_keeps_layout_but_no_personal_values():
    clean = sanitize_sample(SAMPLE)
    assert "MARIA" not in clean and "maria.prueba" not in clean and "banco.example" not in clean
    assert "Hola <nombre>" in clean
    assert "CRC 99.999,99" in clean and "99/99/9999" in clean and "999999999999" in clean
    assert residual_risks(clean) == []


def test_unsanitized_samples_are_never_sent():
    sent = []
    with pytest.raises(ValueError, match="not safe to send"):
        discovery.propose([SAMPLE], sender=lambda prompt: sent.append(prompt))
    assert sent == []


VALID = {
    "bank": "banco_ejemplo", "sender_domains": ["banco.example"], "subject_pattern": r"(?i)compra",
    "fields": {"amount": r"Monto:\s*CRC\s*(?P<value>[\d.,]+)", "date": r"Fecha:\s*(?P<value>\d{2}/\d{2}/\d{4})"},
    "currency_hint": "CRC", "direction": {"income_keywords": ["deposito"], "expense_keywords": ["compra"]},
    "status": "ACTIVE", "notes": "fits both samples",
}


def test_a_proposal_is_always_pending_and_evaluated_deterministically():
    result = discovery.propose([sanitize_sample(SAMPLE)], sender=lambda prompt: (json.loads(json.dumps(VALID)), "test-model"))
    assert result["status"] == PENDING, "the model can never mark its own proposal active"
    assert result["approved_by"] is None
    assert result["evaluation"] == [{"fields": {"amount": "99.999,99", "date": "99/99/9999"}, "direction": "out", "complete": True}]


@pytest.mark.parametrize("broken", [
    {**VALID, "fields": {}},
    {**VALID, "fields": {"amount": "Monto (unclosed"}},
    {**VALID, "fields": {"amount": r"Monto:\s*(?P<x>\d+)"}},
    {**VALID, "subject_pattern": "a" * 400},
])
def test_invalid_proposals_are_rejected(broken):
    with pytest.raises((ValueError, Exception)):
        discovery.validate_proposal(broken, source_model="test-model")


def test_provider_requires_explicit_opt_in_and_key(monkeypatch):
    monkeypatch.delenv("PARSER_DISCOVERY_ENABLED", raising=False)
    monkeypatch.setattr(discovery.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    with pytest.raises(RuntimeError, match="PARSER_DISCOVERY_ENABLED"):
        discovery.openai_sender("prompt")
    monkeypatch.setenv("PARSER_DISCOVERY_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        discovery.openai_sender("prompt")


def test_cli_dry_run_prints_sanitized_text_and_sends_nothing(tmp_path, monkeypatch, capsys):
    sample = tmp_path / "sample.txt"
    sample.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(discovery.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert propose_parser.main([str(sample)]) == 0
    output = capsys.readouterr().out
    assert "MARIA" not in output and "15.000" not in output and "Dry run" in output


def test_live_ingestion_never_imports_discovery_or_a_second_ai_provider():
    ingestion = ["gmail_service", "microsoft_mail", "financial_candidate", "statement_candidate", "candidate_resolution"]
    for path in [*BACKEND.glob("email_monitor/*.py"), *BACKEND.glob("importers/*.py"), *(BACKEND / "user_product" / f"{name}.py" for name in ingestion)]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        modules |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert not any(m.startswith(("backend.parser_discovery", "backend.ai", "google.genai", "openai")) for m in modules), path


def test_gemini_is_gone():
    requirements = (BACKEND.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "google-genai" not in requirements
    for path in BACKEND.rglob("*.py"):
        if path.resolve() != Path(__file__).resolve():
            assert "gemini_client" not in path.read_text(encoding="utf-8"), path
