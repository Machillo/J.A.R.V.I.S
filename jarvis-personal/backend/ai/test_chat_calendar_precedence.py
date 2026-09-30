"""JARVIS chat: an explicit calendar order is a calendar event, even when it is about a trip.

"Agendá el viaje de Ecuador para el 11 de octubre" used to reach the travel/goal planner, because
the chat's travel, purchase and debt shortcuts ran before the calendar intent the router had
already detected. Explicit calendar orders (a calendar verb first, and a date) now reach the
calendar flow with its confirmation; every other travel, purchase or debt message keeps its
historical answer. The shortcuts are recorded, not run: nothing touches a database.
"""
from __future__ import annotations

import pytest

from backend.ai import decision_engine, jarvis_engine
from backend.ai.intent_router import is_explicit_calendar_command
from backend.ai.test_chat_confirmation import chat  # noqa: F401  (the in-memory chat fixture)


@pytest.fixture
def routes(chat, monkeypatch):  # noqa: F811
    """The real chat routing; the travel/purchase decision, goal planner and debt advisory answer a marker."""
    def decision(message):
        kind = decision_engine.classify_decision_request(message)
        return {"message": f"decision:{kind}", "intent": f"decision_{kind}", "status": "OK", "pending": False} if kind else None

    monkeypatch.setattr(jarvis_engine, "handle_personal_decision_request", decision)
    monkeypatch.setattr(jarvis_engine, "plan_long_term_goal", lambda message: {"status": "OK", "message": "goal planner", "scenarios": []})
    monkeypatch.setattr(jarvis_engine, "get_debt_advisory", lambda: {"status": "OK", "message": "debt advisory"})
    return chat


@pytest.mark.parametrize("message", [
    "Agenda el viaje de Ecuador para el 11 de octubre",
    "Agendá el viaje de Ecuador para el 11 de octubre",
    "Agendá el viaje a Ecuador para el 11 de octubre",
    "Agendar viaje a Ecuador el 11 de octubre",
    "Agendame el viaje de Ecuador el 11 de octubre",
    "Recordame el viaje de Ecuador el 11 de octubre",
    "Recuérdame el viaje a Ecuador mañana",
    "JARVIS, agendá el viaje de Ecuador el 11/10",
])
def test_an_explicit_calendar_order_about_a_trip_is_a_calendar_event(routes, message):
    first = jarvis_engine.process_message(message)
    assert first["intent"] == "create_calendar_event"
    assert first["status"] == "PENDING" and first["pending"] is True  # J1: shown first
    assert "viaje" in first["message"] and "Ecuador" in first["message"]
    assert routes["writes"] == []

    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK"
    [(name, _, kwargs)] = routes["writes"]
    assert name == "event" and "Ecuador" in kwargs["title"] and kwargs["event_type"] == "personal"


def test_the_historical_dentist_order_is_still_a_calendar_event(routes):
    first = jarvis_engine.process_message("Agendá dentista para el 11 de octubre")
    assert first["intent"] == "create_calendar_event" and first["pending"] is True
    jarvis_engine.process_message("sí")
    assert [name for name, *_ in routes["writes"]] == ["event"]


@pytest.mark.parametrize("message, calendar_word", [
    ("Agendá comprar regalos el 11 de octubre", "comprar"),      # the purchase shortcut
    ("Agendá pagar deuda del BAC el 11 de octubre", "deuda"),     # the debt shortcut
])
def test_an_explicit_calendar_order_about_money_is_a_calendar_event(routes, message, calendar_word):
    first = jarvis_engine.process_message(message)
    assert first["intent"] == "create_calendar_event" and calendar_word in first["message"]
    assert routes["writes"] == []


@pytest.mark.parametrize("message, intent, answer", [
    # Travel questions and plans keep the travel decision and the goal planner.
    ("Tengo un viaje a Ecuador, ¿puedo pagarlo?", "decision_travel", "decision:travel"),
    ("Quiero ahorrar para viajar a Ecuador", "decision_travel", "decision:travel"),
    ("Quiero ir a Ecuador en diciembre", "decision_travel", "decision:travel"),
    ("Quiero hacer un viaje de fin de año", "goal_planning", "goal planner"),
    # Without a date it is not a calendar order: "agendá un viaje a Japón" stays a travel decision.
    ("Agendá un viaje a Japón", "decision_travel", "decision:travel"),
    # Purchases and debts keep their shortcuts too.
    ("¿Puedo comprar un celular nuevo?", "decision_purchase", "decision:purchase"),
    ("Quiero abonar a la tarjeta", "debt_advisory", "debt advisory"),
])
def test_travel_purchase_and_debt_messages_keep_their_answers(routes, message, intent, answer):
    reply = jarvis_engine.process_message(message)
    assert reply["intent"] == intent and reply["message"].startswith(answer)
    assert routes["writes"] == []


@pytest.mark.parametrize("message, expected", [
    ("Agenda el viaje de Ecuador para el 11 de octubre", True),
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
