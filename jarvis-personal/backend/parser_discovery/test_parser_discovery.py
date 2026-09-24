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
    "Hola MARIA PRUEBA:\nBanco Ejemplo le informa una compra en SUPER ESQUINA\n"
    "Monto: CRC 15.000,00\nFecha: 22/09/2026\nReferencia: 123456789012\n"
    "Contacto: maria.prueba@example.com https://banco.example/x?id=4455"
)


def test_sanitizer_keeps_layout_but_no_personal_values():
    clean = sanitize_sample(SAMPLE)
    for private in ("MARIA", "PRUEBA", "SUPER", "ESQUINA", "maria.prueba", "banco.example", "4455", "15.000", "22/09/2026"):
        assert private not in clean
    assert clean.startswith("Hola <w> <w>:")
    assert "Monto: CRC 99.999,99" in clean and "Fecha: 99/99/9999" in clean and "Referencia: 999999999999" in clean
    assert residual_risks(clean) == []


HOSTILE = (
    "Estimado(a) Juan Carlos Pérez Mora,\n"
    "SINPE Móvil a nombre de Ana Lucía Vargas Rojas por ₡15.000,00\n"
    "Sr. Pedro Solano, Remitente: Pedro Solano Quesada Destino: María Fernández\n"
    "Tarjetahabiente\nPEDRO SOLANO\n"
    "Detalle: consulta psiquiátrica www.banco.example/verify?token=abc juan [at] gmail.com juan.perez@gmail .com\n"
    "IBAN CR05015202001026284066 cédula 1-1234-5678"
)


def test_sanitizer_masks_every_non_banking_word():
    clean = sanitize_sample(HOSTILE)
    for private in ("Juan", "Pérez", "Ana", "Lucía", "Pedro", "PEDRO", "Solano", "María", "psiquiátrica", "banco.example", "token", "gmail", "0152"):
        assert private not in clean, private
    assert sanitize_sample(clean) == clean, "idempotent, so a reviewed file can be verified before sending"


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


def test_bank_name_cannot_escape_the_output_folder():
    proposal = discovery.validate_proposal({**VALID, "bank": "../../etc/Banco X"}, source_model="test-model")
    assert proposal["bank"] == "etc_banco_x"


@pytest.mark.parametrize("broken", [
    {**VALID, "fields": {}},
    {**VALID, "fields": {"amount": "Monto (unclosed"}},
    {**VALID, "fields": {"amount": r"Monto:\s*(?P<x>\d+)"}},
    {**VALID, "subject_pattern": "a" * 400},
])
def test_invalid_proposals_are_rejected(broken):
    with pytest.raises(ValueError):
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


def test_cli_sends_only_reviewed_sanitized_files(tmp_path, monkeypatch, capsys):
    raw = tmp_path / "sample.txt"
    raw.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "proposals"
    monkeypatch.setattr(discovery.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert propose_parser.main([str(raw), "--out", str(out)]) == 0
    output = capsys.readouterr().out
    assert "MARIA" not in output and "15.000" not in output and "Nothing was sent" in output
    sanitized = out / "sample.sanitized.txt"
    assert sanitized.read_text(encoding="utf-8") == sanitize_sample(SAMPLE)
    # Raw files, renamed raw files and edited sanitized files are refused before any network call.
    assert propose_parser.main(["--send", str(raw), "--out", str(out)]) == 1
    renamed = out / "raw.sanitized.txt"
    renamed.write_text(SAMPLE, encoding="utf-8")
    assert propose_parser.main(["--send", str(renamed), "--out", str(out)]) == 1


@pytest.mark.parametrize("pattern", [r"(?P<value>(\w+\s?)+)!", r"(?P<value>((ab)*)*)"])
def test_backtracking_patterns_are_refused(pattern):
    with pytest.raises(ValueError, match="nested"):
        discovery.validate_proposal({**VALID, "fields": {"amount": pattern}}, source_model="test-model")


def test_malformed_model_output_fails_cleanly():
    with pytest.raises(ValueError):
        discovery.validate_proposal({**VALID, "direction": "in"}, source_model="test-model")


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
