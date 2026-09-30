"""JARVIS Chat's scope (Owner decision, J2): quick payroll records and the agenda, nothing else.

- OT, VGH, holidays and bonuses keep their historical parsing and amounts, shown first and saved
  only on "sí" (J1).
- An explicit agenda order with a date ("Agendá el viaje a Ecuador el 11 de octubre") is a calendar
  event whatever it is about: a trip, a card, a race, a purchase.
- Travel, purchase, goal, debt, strategy, finance, sports, memory and search requests get a short
  "not available here" and run none of those engines; they stay in the backend for other modules.

In-memory stubs only (the `chat` fixture of test_chat_confirmation); nothing touches a database.
"""
from __future__ import annotations

import inspect

import pytest

from backend.advisor import service as advisor_service
from backend.ai import decision_engine, jarvis_engine
from backend.ai.intent_router import is_explicit_calendar_command
from backend.ai.test_chat_confirmation import chat  # noqa: F401  (the in-memory chat fixture)
from backend.finance import intelligence, strategic_engine
from backend.finance import service as finance_service
from backend.integrations import internet_search
from backend.sports import service as sports_service

# The engines that used to answer from the chat and must never run from it again.
RETIRED_ENGINES = {
    decision_engine: ["handle_personal_decision_request", "handle_decision_pending_action", "classify_decision_request"],
    intelligence: ["plan_long_term_goal", "get_debt_advisory"],
    strategic_engine: ["get_financial_engine_report", "simulate_what_if"],
    advisor_service: ["get_financial_advice", "analyze_spending_habits"],
    finance_service: ["get_debts", "get_net_worth_report", "get_user_status"],
    sports_service: ["get_sports_calendar_summary"],
    internet_search: ["internet_search"],
}


@pytest.fixture
def scoped(chat, monkeypatch):  # noqa: F811
    """The chat, with every retired engine made to fail loudly if anything still calls it."""
    for module, names in RETIRED_ENGINES.items():
        for name in names:
            def forbidden(*_args, _name=name, **_kwargs):
                raise AssertionError(f"JARVIS Chat must not run {_name}")
            monkeypatch.setattr(module, name, forbidden)
    return chat


# 1. Quick payroll records -------------------------------------------------------------------

def test_one_hour_of_ot_is_shown_then_recorded_on_yes(scoped):
    first = jarvis_engine.process_message("Hoy hice 1 hora de OT")
    assert first["action_type"] == "create_payroll_event" and first["pending"] is True
    assert "₡3,000.00" in first["message"]  # 1 h × 2000 × 1.5, the historical formula
    assert scoped["writes"] == []
    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK"
    assert [(name, kwargs["event_type"], kwargs["hours"]) for name, _, kwargs in scoped["writes"]] == [("payroll_event", "ot", 1.0)]


def test_a_bonus_is_shown_then_recorded_on_yes(scoped):
    first = jarvis_engine.process_message("Hoy me llegaron 50000 de bono")
    assert first["action_type"] == "create_bonus" and first["pending"] is True
    assert "₡50,000.00" in first["message"]
    assert scoped["writes"] == []
    jarvis_engine.process_message("sí")
    assert [(name, kwargs["amount"]) for name, _, kwargs in scoped["writes"]] == [("bonus", 50000.0)]


# 2. The agenda ------------------------------------------------------------------------------

@pytest.mark.parametrize("message, title_word", [
    ("Agenda el viaje a Ecuador para el 11 de octubre", "Ecuador"),
    ("Agendá pagar la tarjeta el 11 de octubre", "tarjeta"),
    ("Recordame ver la F1 el 11 de octubre", "F1"),
    ("Agendá comprar llantas el 11 de octubre", "llantas"),
    # The same order in the other verbs the calendar already knows.
    ("Agendá el viaje de Ecuador para el 11 de octubre", "Ecuador"),
    ("Agendar viaje a Ecuador el 11 de octubre", "Ecuador"),
    ("Agendame la carrera de F1 el 11 de octubre", "F1"),
    ("Recuérdame la inversión en el banco el 11 de octubre", "inversión"),
    ("Agendá cena en el restaurante mañana a las 8pm", "restaurante"),
    ("Agendá cobrar el bono de 50000 el 11 de octubre", "bono"),
    ("JARVIS, agendá la deuda del carro el 11/10", "carro"),
])
def test_an_agenda_order_is_a_calendar_event_whatever_it_is_about(scoped, message, title_word):
    first = jarvis_engine.process_message(message)
    assert first["intent"] == "create_calendar_event" and first["action_type"] == "create_calendar_event"
    assert first["status"] == "PENDING" and first["pending"] is True
    assert title_word in first["message"]
    assert scoped["writes"] == []  # before "sí": no event

    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK"
    [(name, _, kwargs)] = scoped["writes"]  # after "sí": exactly one event
    assert name == "event" and title_word in kwargs["title"] and kwargs["event_type"] == "personal"


def test_the_historical_dentist_order_is_still_a_calendar_event(scoped):
    first = jarvis_engine.process_message("Agendá dentista para el 11 de octubre")
    assert first["intent"] == "create_calendar_event" and first["pending"] is True
    jarvis_engine.process_message("sí")
    assert [name for name, *_ in scoped["writes"]] == ["event"]


def test_an_agenda_order_without_a_date_asks_for_it(scoped):
    # The calendar's historical question, not the travel planner.
    answer = jarvis_engine.process_message("Agendá un viaje a Japón")
    assert answer["intent"] == "create_calendar_event" and answer["status"] == "NEEDS_DATE"
    assert answer["pending"] is False and scoped["writes"] == [] and scoped["pending"] is None


def test_que_tengo_answers_from_the_agenda(scoped, monkeypatch):
    monkeypatch.setattr(jarvis_engine, "calendar_summary", lambda: {
        "status": "OK", "message": "Señor, estos son sus próximos compromisos.",
        "events": [{"event_date": "2026-10-11 09:00", "title": "el viaje a Ecuador para"}]})
    answer = jarvis_engine.process_message("¿Qué tengo?")
    assert answer["intent"] == "calendar_summary" and "2026-10-11 09:00: el viaje a Ecuador" in answer["message"]
    assert scoped["writes"] == []


# 3. Everything else is outside JARVIS Chat --------------------------------------------------

@pytest.mark.parametrize("message", [
    "Tengo un viaje a Ecuador, ¿puedo pagarlo?",
    "¿Puedo comprar un carro?",
    "¿Cómo pago mis deudas?",
    "Quiero ahorrar para viajar",
    "Quiero ir a Ecuador",
    "Quiero abonar a la tarjeta",
    "Ejecutá mi estrategia",
    "¿Cuál es mi mayor deuda?",
    "¿Cómo estoy financieramente?",
    "¿Qué pasa si compro un celular en 12 cuotas de 30000?",
    "Agregá una deuda de 100000",
    "Registrá un gasto de 5000 en comida",
    "Quiero crear una meta",
    "Busca en internet el clima de Quito",
    "¿Cuándo es la próxima carrera de F1?",
])
def test_other_requests_run_no_engine_and_write_nothing(scoped, message):
    answer = jarvis_engine.process_message(message)
    assert answer["status"] == "UNSUPPORTED" and answer["pending"] is False, message
    assert "no está disponible en JARVIS Chat" in answer["message"]
    assert scoped["writes"] == [] and scoped["pending"] is None


def test_a_pending_action_the_chat_no_longer_handles_is_never_saved(scoped):
    # A debt left pending before J2, waiting for "sí": it is cancelled, never saved.
    scoped["pending"] = {"id": 3, "action_type": "create_debt", "current_field": "confirm", "missing_fields": [],
                         "payload": {"name": "Tarjeta", "total_amount": 100000.0}}
    answer = jarvis_engine.process_message("sí")
    assert "cancelé un registro pendiente que JARVIS Chat ya no maneja" in answer["message"]
    assert scoped["pending"] is None and scoped["writes"] == []


def test_the_chat_no_longer_imports_the_retired_engines():
    # Structural guard: reconnecting one of them to the chat needs an import that fails here.
    for module, names in RETIRED_ENGINES.items():
        for name in names:
            assert not hasattr(jarvis_engine, name), f"jarvis_engine imports {module.__name__}.{name}"
    source = inspect.getsource(jarvis_engine)
    for retired in ["decision_engine", "finance.intelligence", "strategic_engine", "advisor.service", "sports.service",
                    "internet_search", "memory_service", "fixed_expenses", "goals.service"]:
        assert retired not in source, retired


# The explicit agenda order --------------------------------------------------------------------

@pytest.mark.parametrize("message, expected", [
    ("Agenda el viaje a Ecuador para el 11 de octubre", True),
    ("agendá dentista mañana a las 3pm", True),
    ("Recuérdame pagar el agua el 15/10", True),
    ("Agendá un viaje a Japón", False),                         # no date
    ("Tengo un viaje a Ecuador el 11 de octubre", False),       # no calendar verb first
    ("Quiero ahorrar para viajar a Ecuador en octubre", False),
    ("Programá el viaje para el 11 de octubre", False),         # not a verb the calendar parser knows
    ("", False),
])
def test_an_explicit_calendar_order_needs_a_calendar_verb_first_and_a_date(message, expected):
    assert is_explicit_calendar_command(message) is expected
