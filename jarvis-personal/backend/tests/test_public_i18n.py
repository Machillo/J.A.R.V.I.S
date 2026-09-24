"""DINCR public text follows the app language (Accept-Language: es|en).

Localization must never change a financial decision: every rule is run in
both languages and the results must match except for the human-readable text.
"""
import ast
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import main
from backend.ai import strategy_dashboard
from backend.auth import saas
from backend.core.i18n import current_language, language_for_request, resolve_language, use_language
from backend.finance import intelligence
from backend.financial_lifecycle import state as lifecycle_state
from backend.financial_lifecycle.monthly_review import build_monthly_review, localized_action
from backend.financial_lifecycle.proactive import build_proactive_advisor
from backend.user_product import mail_copy, strategy_engine

BACKEND = Path(__file__).resolve().parents[1]
SPANISH = re.compile(r"[áéíóúñ¿¡]|\b(de|del|la|las|los|tu|tus|con|para|por|sin|que|meta|metas|deuda|deudas|pago|gasto|ingreso|mes|meses|cuenta|fondo|Señor)\b", re.I)
TEXT_KEYS = {
    "recommendation", "warnings", "label", "director_note", "message", "title", "detail", "explanation",
    "headline", "summary", "rationale", "mode_reason", "mode_label", "why", "context", "action", "note",
    "name", "tagline", "features", "reason", "investment_blockers", "rule", "blocked_by",
}


def in_both(fn, *args, **kwargs):
    with use_language("es"):
        spanish = fn(*args, **kwargs)
    with use_language("en"):
        english = fn(*args, **kwargs)
    return spanish, english


# Raw stored actions carried for audit (never rendered); they stay canonical.
DATA_KEYS = {"evidence", "strategy_evolution"}


def texts(value, key=None):
    """Every human-readable string under a text key."""
    if isinstance(value, dict):
        return [text for k, v in value.items() if k not in DATA_KEYS for text in texts(v, k)]
    if isinstance(value, list):
        return [text for item in value for text in texts(item, key)]
    return [value] if isinstance(value, str) and key in TEXT_KEYS and value.strip() else []


def assert_same_decision(spanish, english, key=None):
    """Same structure, numbers, codes and flags; only text keys may differ."""
    assert type(spanish) is type(english), key
    if isinstance(spanish, dict):
        assert spanish.keys() == english.keys(), key
        for k in spanish:
            assert_same_decision(spanish[k], english[k], k)
    elif isinstance(spanish, list):
        assert len(spanish) == len(english), key
        for a, b in zip(spanish, english):
            assert_same_decision(a, b, key)
    elif not (isinstance(spanish, str) and key in TEXT_KEYS):
        assert spanish == english, f"{key}: {spanish!r} != {english!r}"


def assert_languages(spanish, english, *, user_names=()):
    es_texts, en_texts = texts(spanish), texts(english)
    assert es_texts and en_texts and len(es_texts) == len(en_texts)
    assert any(SPANISH.search(text) for text in es_texts), es_texts
    for es_text, en_text in zip(es_texts, en_texts):
        stripped = en_text
        for name in user_names:
            stripped = stripped.replace(name, "")
        assert not SPANISH.search(stripped), f"Spanish in English response: {en_text!r}"
        # An untranslated string is identical in both languages.
        if es_text == en_text:
            assert en_text in user_names or not re.search(r"[A-Za-z]{2,} [A-Za-z]{2,}", stripped), f"untranslated: {en_text!r}"


# --- Language resolution ----------------------------------------------------

@pytest.mark.parametrize(("header", "expected"), [
    (None, "es"), ("", "es"), ("es", "es"), ("es-CR,es;q=0.9", "es"), ("en", "en"), ("en-US,en;q=0.9", "en"),
    ("EN", "en"), ("fr-FR", "es"), ("xx;;,,", "es"), ("*", "es"), ("en" * 200, "es"),
])
def test_accept_language_resolution_and_fallback(header, expected):
    assert resolve_language(header) == expected


def test_only_public_dincr_routes_are_localized():
    assert language_for_request("/user-product/vip/command-center", "en") == "en"
    assert language_for_request("/auth/plans", "en") == "en"
    assert language_for_request("/product-ops/health", "en") == "en"
    # DINCR Owner / JARVIS routes keep their Spanish copy.
    for path in ("/jarvis/premium/strategy-dashboard", "/finance/summary", "/advisor/strategy", "/"):
        assert language_for_request(path, "en") == "es"


def test_middleware_sets_the_language_for_sync_handlers():
    app = FastAPI()
    app.middleware("http")(main.language_middleware)

    @app.get("/user-product/probe")
    def probe():
        return {"language": current_language()}

    @app.get("/jarvis/probe")
    def owner_probe():
        return {"language": current_language()}

    client = TestClient(app)
    assert client.get("/user-product/probe", headers={"Accept-Language": "en"}).json() == {"language": "en"}
    assert client.get("/user-product/probe", headers={"Accept-Language": "es"}).json() == {"language": "es"}
    assert client.get("/user-product/probe").json() == {"language": "es"}
    assert client.get("/user-product/probe", headers={"Accept-Language": "de"}).json() == {"language": "es"}
    assert client.get("/jarvis/probe", headers={"Accept-Language": "en"}).json() == {"language": "es"}
    assert current_language() == "es"  # nothing leaks outside the request


# --- Strategy (Basic / VIP) --------------------------------------------------

DEBTS = [
    {"id": 1, "name": "Tarjeta BAC", "remaining_amount": 900_000, "monthly_payment": 60_000, "interest_rate": 48, "payment_day": 5},
    {"id": 2, "name": "Préstamo auto", "remaining_amount": 2_000_000, "monthly_payment": None, "interest_rate": None, "payment_day": 20},
]
SNAPSHOTS = {
    "needs_income": {"monthly_income_estimate": 0, "debts": []},
    "critical": {"monthly_income_estimate": 400_000, "essential_monthly_expenses": 380_000, "debts": DEBTS},
    "debt": {"monthly_income_estimate": 1_200_000, "essential_monthly_expenses": 500_000, "liquid_savings": 50_000,
             "emergency_fund_target": 1_000_000, "debts": DEBTS, "discretionary_monthly_minimum": 40_000,
             "goals": [{"id": 7, "name": "Viaje familiar", "target_amount": 600_000, "current_amount": 50_000,
                        "target_date": "2026-12-01", "priority": "high"}]},
    "no_debt": {"monthly_income_estimate": 900_000, "essential_monthly_expenses": None, "debts": []},
}
USER_NAMES = ("Tarjeta BAC", "Préstamo auto", "Viaje familiar")


@pytest.mark.parametrize("case", SNAPSHOTS)
def test_basic_strategy_es_en_same_decision(case):
    spanish, english = in_both(strategy_engine.build_basic_strategy, SNAPSHOTS[case])
    assert_same_decision(spanish, english)
    assert_languages(spanish, english, user_names=USER_NAMES)


@pytest.mark.parametrize("case", SNAPSHOTS)
def test_vip_strategy_and_alerts_es_en_same_decision(case):
    spanish, english = in_both(strategy_engine.build_vip_strategy, SNAPSHOTS[case])
    assert_same_decision(spanish, english)
    assert_languages(spanish, english, user_names=USER_NAMES)
    alerts_es, alerts_en = in_both(strategy_engine.build_vip_insights, SNAPSHOTS[case])
    assert_same_decision(alerts_es, alerts_en)
    if alerts_es["alerts"]:
        assert_languages(alerts_es, alerts_en, user_names=USER_NAMES)


def test_plural_and_amounts_are_preserved():
    snapshot = {**SNAPSHOTS["debt"], "debts": [DEBTS[1]]}
    spanish, english = in_both(strategy_engine.build_basic_strategy, snapshot)
    assert "1 deuda;" in spanish["warnings"][0] and "1 debt;" in english["warnings"][0]
    spanish, english = in_both(strategy_engine.build_basic_strategy, SNAPSHOTS["critical"])
    amount = re.search(r"\d+\.\d{2}", spanish["recommendation"]).group()
    assert amount in english["recommendation"]


# --- VIP strategy dashboard (director + current priority) ------------------

@pytest.mark.parametrize("available", [0, 400_000])
def test_director_priority_es_en_same_decision(available):
    kwargs = dict(available_before_allocation=available, debts=DEBTS, goal_reserves={"items": []},
                  savings_total=10_000, emergency_monthly_base=300_000)
    director_es, director_en = in_both(strategy_dashboard._build_dynamic_director_allocation, **kwargs)
    assert_same_decision(director_es, director_en)
    assert_languages(director_es, director_en, user_names=USER_NAMES)
    timeline = [{"name": "Tarjeta BAC"}]
    priority_es, priority_en = in_both(strategy_dashboard._build_current_priority,
                                       no_free_cash=available <= 0, director=director_es, timeline=timeline)
    assert priority_es["kind"] == priority_en["kind"]
    assert_languages(priority_es, priority_en, user_names=USER_NAMES)


# --- Debt advisory ------------------------------------------------------------

def test_debt_advisory_es_en_same_numbers(monkeypatch):
    rows = [dict(debt, debt_type=kind) for debt, kind in zip(DEBTS, ("credit_card", "tasa_cero"))]
    rows[1] = {**rows[1], "monthly_payment": 80_000, "interest_rate": 0}

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, *_a, **_k): return SimpleNamespace(fetchall=lambda: [dict(r) for r in rows])

    monkeypatch.setattr(intelligence, "get_current_workspace_id", lambda: "w")
    monkeypatch.setattr(intelligence, "get_real_availability", lambda: {})
    monkeypatch.setattr(intelligence, "get_connection", lambda: Conn())
    for extra in (0, 150_000, 1_000_000):
        spanish, english = in_both(intelligence.get_debt_advisory, extra_cash=extra)
        assert_same_decision(spanish, english)
        assert_languages(spanish, english, user_names=USER_NAMES)
        assert not any(text.startswith("Sir") for text in texts(english))


# --- Proactive advisor and monthly review -----------------------------------

def _state(*, safe=100_000, flow=50_000, debt=500_000, coverage=1.5, health=70, action=None):
    return {
        "balance_sheet": {"net_worth": 1_000_000, "liquid_assets": 200_000},
        "debt": {"total": debt},
        "cashflow": {"safe_available": safe, "net_operational": flow},
        "emergency_fund": {"current": 200_000, "coverage_months": coverage},
        "health": {"score": health},
        "strategy": {"next_action": action or {"type": "debt", "title": "Abonar a Tarjeta BAC", "amount": 50_000, "why": "Tasa más alta."}},
    }


def test_proactive_alerts_es_en_same_decision():
    previous = _state()
    current = _state(safe=-10_000, flow=-20_000, debt=380_000, coverage=3.2, health=52,
                     action={"type": "emergency_fund", "title": "Completar un mes de Salvavidas", "amount": 20_000})
    kwargs = dict(current=current, previous=previous, baseline_date="2026-09-01", as_of=date(2026, 9, 21))
    spanish, english = in_both(build_proactive_advisor, **kwargs)
    assert_same_decision(spanish, english)
    assert_languages(spanish, english)
    assert [a["id"] for a in spanish["alerts"]] == [a["id"] for a in english["alerts"]]
    baseline_es, baseline_en = in_both(build_proactive_advisor, current=current, previous=None, baseline_date=None)
    assert_languages(baseline_es, baseline_en)


def test_monthly_review_es_en_same_decision():
    observations = [
        {"snapshot_date": "2026-08-01", "state": _state()},
        {"snapshot_date": "2026-08-31", "state": _state(debt=420_000, health=75)},
    ]
    closing = _state(debt=420_000, health=75, action={"type": "goal", "title": "Financiar Viaje familiar", "amount": 30_000})
    spanish, english = in_both(build_monthly_review, period="2026-08", closing_state=closing, observations=observations)
    spanish.pop("generated_at"), english.pop("generated_at")
    assert_same_decision(spanish, english)
    assert_languages(spanish, english, user_names=USER_NAMES)
    assert english["next_month"]["title"] == "Fund Viaje familiar"
    baseline_es, baseline_en = in_both(build_monthly_review, period="2026-08", closing_state=closing, observations=observations[:1])
    baseline_es.pop("generated_at"), baseline_en.pop("generated_at")
    assert_same_decision(baseline_es, baseline_en)


def test_stored_actions_are_translated_without_changing_them():
    action = {"type": "debt", "title": "Abonar a Tarjeta BAC", "why": "Doctor Strange comparó las rutas posibles.", "amount": 1}
    with use_language("es"):
        assert localized_action(action) == ("Abonar a Tarjeta BAC", "Doctor Strange comparó las rutas posibles.")
    with use_language("en"):
        assert localized_action(action) == ("Pay extra toward Tarjeta BAC", "It’s the priority debt in your current strategy.")
        assert localized_action({"type": "unknown", "title": "Algo nuevo"}) == (None, None)
    assert action["title"] == "Abonar a Tarjeta BAC"


def test_persisted_financial_state_is_always_canonical_spanish(monkeypatch):
    monkeypatch.setattr(lifecycle_state, "_build_financial_state", lambda: {"language": current_language()})
    with use_language("en"):
        assert lifecycle_state.build_financial_state() == {"language": "es"}
        assert current_language() == "en"


# --- Gmail / Outlook stored reasons --------------------------------------------

def _parser_reasons():
    reasons = set()
    for relative in ("email_monitor/parser.py", "email_monitor/popular_pdf.py", "email_monitor/personal_rules.py",
                     "user_product/payroll_income.py", "user_product/gmail_service.py"):
        tree = ast.parse((BACKEND / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in {"_ignored", "_internal_ignored"}:
                reasons.update(a.value for a in node.args[4:5] if isinstance(a, ast.Constant))
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value in {"confidence_reason", "ignore_reason"}
                            and isinstance(value, ast.Constant) and value.value):
                        reasons.add(value.value)
            if isinstance(node, ast.keyword) and node.arg in {"ignore_reason", "confidence_reason"} and isinstance(node.value, ast.Constant):
                reasons.add(node.value.value)
            if (isinstance(node, ast.BoolOp) and isinstance(node.values[-1], ast.Constant)
                    and isinstance(node.values[-1].value, str) and node.values[-1].value.startswith("Estado de cuenta")):
                reasons.add(node.values[-1].value)
            if (isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "reason" for t in node.targets)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                reasons.add(node.value.value)
    return reasons


def test_every_parser_reason_has_an_english_translation():
    missing = sorted(reason for reason in _parser_reasons() if reason not in mail_copy.ENGLISH_REASONS)
    assert missing == []


def test_parse_reasons_es_en():
    with use_language("es"):
        assert mail_copy.localized_parse_reason("Correo bancario sin plantilla confiable. No se genera candidato.").startswith("Correo")
    with use_language("en"):
        assert mail_copy.localized_parse_reason("Orden patronal CCSS 2026-08 procesada.") == "CCSS payroll order 2026-08 processed."
        assert mail_copy.localized_parse_reason("Estado de cuenta procesado: 1 movimiento(s) listos para revisión.") == \
            "Statement processed: 1 transaction ready for review."
        assert mail_copy.localized_parse_reason("Motivo desconocido de una versión anterior.") == mail_copy.UNKNOWN_REASON
        assert mail_copy.localized_parse_reason(None) is None


# --- Plans ---------------------------------------------------------------------

def test_plan_copy_es_en_same_plans():
    assert saas.PLAN_COPY.keys() == saas.PLAN_COPY_EN.keys()
    for code in saas.PLAN_COPY:
        assert len(saas.PLAN_COPY[code]["features"]) == len(saas.PLAN_COPY_EN[code]["features"])
        assert_languages(saas.PLAN_COPY[code], saas.PLAN_COPY_EN[code])


# --- Regression guard: public narrative must go through tx() -----------------

# Functions whose returned text reaches the public DINCR app. A Spanish string
# literal in them must be an argument of tx()/localized()/plural().
PUBLIC_TEXT_FUNCTIONS = {
    "user_product/strategy_engine.py": {"build_basic_strategy", "build_vip_strategy", "build_vip_insights", "build_paycheck_plan"},
    "user_product/vip_service.py": {"get_vip_command_center"},
    "ai/strategy_dashboard.py": {"_build_dynamic_director_allocation", "_build_current_priority"},
    "finance/intelligence.py": {"get_debt_advisory"},
    "finance/emergency_fund.py": {"get_salvavidas_state"},
    "financial_lifecycle/proactive.py": {"build_proactive_advisor"},
    "financial_lifecycle/monthly_review.py": {"build_monthly_review", "_scorecard", "_headline", "_summary", "_value_explanation", "_next_month"},
    "financial_lifecycle/progress.py": {"_transition_reason"},
    "user_product/basic_service.py": {"get_financial_calendar"},
    "goals/strategy.py": {"build_goal_portfolio"},
}
LOCALIZERS = {"tx", "localized", "plural"}
# Canonical values compared or stored (not copy): debt keywords, category names,
# and the director mode labels, which are English in both languages (shared
# JARVIS vocabulary; DINCR renders mode_reason/priority, never the label).
CANONICAL = re.compile(r"^(GOAL PROTECTION|DEBT \+ SAFETY|DEBT ATTACK|WEALTH BUILDING|prestamo|préstamo|minicuota|tasa cero|reloj|tarjeta bac|banco popular|deuda|críti?ca|critica|alta|casa|vivienda|línea|linea|teléfono|telefono|telefonía|telefonia|Gastos fijos|Comida|Transporte|Personal|Ahorro y metas|Otros|prioritaria|deuda prioritaria)$", re.I)


def _unlocalized_strings(relative, functions):
    tree = ast.parse((BACKEND / relative).read_text(encoding="utf-8"))
    found = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in functions):
        parents = {child: parent for parent in ast.walk(fn) for child in ast.iter_child_nodes(parent)}
        docstring = ast.get_docstring(fn, clean=False)
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or node.value == docstring:
                continue
            value = node.value.strip()
            human = SPANISH.search(value) or re.search(r"[A-Za-zÁÉÍÓÚáéíóúñ]{2,} [A-Za-zÁÉÍÓÚáéíóúñ]{2,}", value)
            if not human or CANONICAL.match(value):
                continue
            parent, inside = parents.get(node), False
            while parent is not None:
                if isinstance(parent, ast.Call) and getattr(parent.func, "id", None) in LOCALIZERS:
                    inside = True
                    break
                if (isinstance(parent, ast.Tuple) and len(parent.elts) == 2
                        and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in parent.elts)):
                    inside = True  # ("español", "English") pair resolved with tx(*pair)
                    break
                if isinstance(parent, ast.Call) and getattr(parent.func, "attr", "") in {"execute", "warning", "info", "debug", "error"}:
                    inside = True  # SQL and logs are not user copy
                    break
                parent = parents.get(parent)
            if not inside:
                found.append(f"{relative}:{node.lineno} {node.value[:70]!r}")
    return found


def test_public_narrative_is_localized():
    problems = [problem for relative, functions in PUBLIC_TEXT_FUNCTIONS.items()
                for problem in _unlocalized_strings(relative, functions)]
    assert problems == []
