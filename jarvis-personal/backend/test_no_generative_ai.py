"""Launch invariant: the DINCR production runtime has no generative-AI provider.

DINCR Owner's private assistant (OpenAI) was retired before launch. Nothing the
API process can import may contact a generative-AI provider, so no data, and in
particular no data derived from Google Workspace APIs (Gmail), can be sent to
one. Parser Discovery is offline developer tooling (backend/scripts) and must
stay outside the application import graph.
"""
import ast
from pathlib import Path

import pytest

from backend.ai import jarvis_engine, routes as internal_ai_routes
from backend.ai.intent_router import detect_intent
from backend.ai.response_formatter import format_jarvis_response
from backend.sports import service as sports_service

BACKEND = Path(__file__).resolve().parent
PROVIDER_MARKERS = (
    "api.openai.com", "openai.azure.com", "OPENAI_API_KEY",
    "generativelanguage.googleapis.com", "aiplatform.googleapis.com", "GEMINI",
    "api.anthropic.com", "api.mistral.ai", "api.cohere", "api.groq.com",
)
PROVIDER_SDKS = ("openai", "anthropic", "google.genai", "google.generativeai", "vertexai", "langchain", "cohere", "mistralai")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module and not node.level}
    modules |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    return modules


def _module_file(module: str) -> Path | None:
    parts = module.split(".")[1:]
    for candidate in (BACKEND.joinpath(*parts).with_suffix(".py"), BACKEND.joinpath(*parts, "__init__.py")):
        if candidate.is_file():
            return candidate
    return None


def _application_import_graph() -> set[Path]:
    """Every backend module the API process can load, lazy imports included."""
    seen: set[Path] = set()
    pending = [BACKEND / "main.py"]
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        for module in _imports(path):
            if module == "backend" or module.startswith("backend."):
                target = _module_file(module)
                if target:
                    pending.append(target)
    return seen


def test_no_application_module_can_reach_a_generative_ai_provider():
    graph = _application_import_graph()
    assert BACKEND / "user_product" / "gmail_service.py" in graph  # the walk really covers ingestion
    for path in graph:
        text = path.read_text(encoding="utf-8")
        assert not [marker for marker in PROVIDER_MARKERS if marker in text], path
        assert not [m for m in _imports(path) if m.split(".")[0] in PROVIDER_SDKS or m.startswith(PROVIDER_SDKS)], path


def test_parser_discovery_stays_outside_the_application():
    graph = _application_import_graph()
    assert not [path for path in graph if "parser_discovery" in path.parts or "scripts" in path.parts]


def test_no_generative_ai_sdk_is_a_runtime_dependency():
    requirements = (BACKEND.parent / "requirements.txt").read_text(encoding="utf-8").lower()
    for sdk in ("openai", "anthropic", "google-genai", "google-generativeai", "vertexai", "langchain"):
        assert sdk not in requirements


def test_retired_ai_modules_are_gone():
    for name in ("openai_client", "usage_tracker", "web_access"):
        assert not (BACKEND / "ai" / f"{name}.py").exists()


def test_ai_usage_and_budget_routes_are_gone():
    paths = {route.path for route in internal_ai_routes.router.routes}
    assert not paths & {"/jarvis/usage/today", "/jarvis/usage/admin", "/jarvis/premium/status", "/jarvis/premium/guides"}


@pytest.fixture
def no_database_or_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("this path must not read data or call out")

    monkeypatch.setattr("requests.post", forbidden)
    monkeypatch.setattr("requests.get", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("backend.core.database.get_connection", forbidden)


def test_unhandled_owner_message_builds_no_financial_context(no_database_or_network):
    result = jarvis_engine.answer_with_context("¿qué opinás de mi vida?", {"intent": "general"})

    assert result["status"] == "UNSUPPORTED"
    assert result["source"] == "deterministic"
    assert "data" not in result
    assert not hasattr(jarvis_engine, "build_financial_context")


def test_intent_detection_and_wording_are_deterministic(no_database_or_network):
    assert detect_intent("una frase sin intención conocida")["source"] == "deterministic"
    message = format_jarvis_response("mayor deuda", "highest_debt", {"debt": {"name": "Tarjeta", "remaining_amount": 1000.0}})
    assert message.startswith("Señor, su deuda más alta")


def test_sports_digest_background_job_uses_the_search_result_only(no_database_or_network):
    answer = sports_service._concise_sports_answer(
        "all", "radar", "", {"status": "OK", "results": [{"title": "Evento", "snippet": "Domingo 10:00"}]},
    )
    assert answer == "Señor, encontré esto: Evento. Domingo 10:00"


def test_owner_app_no_longer_calls_ai_usage_or_budget_endpoints():
    source = BACKEND.parent / "frontend" / "src"
    for path in [*source.rglob("*.js"), *source.rglob("*.jsx")]:
        text = path.read_text(encoding="utf-8")
        assert "/jarvis/usage" not in text and "/jarvis/premium/status" not in text and "/jarvis/premium/guides" not in text, path
