"""JARVIS chat (J1): a pending question is never answered, or cancelled, by a message that is also
another request. JARVIS asks: "es la respuesta" uses the text as written, "es otra consulta" answers
it as a normal request and keeps the pending action where it was. Messages the flow always took
(numbers, yes/no) go on exactly as before. Shown on the flows JARVIS Chat keeps (J2): payroll
records and the agenda. In-memory stubs only (the `chat` fixture of test_chat_confirmation);
nothing touches a database.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from backend.ai import action_flow, chat_memory, jarvis_engine
from backend.ai.test_chat_confirmation import chat  # noqa: F401  (the shared in-memory chat)


@pytest.fixture
def records(chat, monkeypatch):  # noqa: F811
    """The chat, with "¿qué tengo?" answered from a stub agenda."""
    monkeypatch.setattr(jarvis_engine, "calendar_summary",
                        lambda: {"status": "OK", "events": [], "message": "Señor, no tiene compromisos próximos."})
    return chat


def _ask(chat, *messages):
    answer = None
    for message in messages:
        answer = jarvis_engine.process_message(message)
    return answer


@pytest.mark.parametrize("opening, question, ambiguous, field, action_type", [
    ("registra un bono", "¿Cuál es el monto del bono?", "Hoy 50000", "amount", "create_bonus"),
    ("registra horas extra", "¿Cuántas horas son?", "mañana 3", "hours", "create_payroll_event"),
    ("registra un bono", "¿Cuál es el monto del bono?", "¿qué tengo?", "amount", "create_bonus"),
])
def test_a_message_that_is_also_another_request_is_asked_about(records, opening, question, ambiguous, field, action_type):
    started = _ask(records, opening)
    assert started["status"] == "PENDING" and question in started["message"]
    before = dict(records["pending"])

    asked = jarvis_engine.process_message(ambiguous)
    # Not saved as the field, not cancelled, the other request not run: JARVIS asks.
    assert asked["status"] == "PENDING" and asked["pending"] is True
    assert asked["data"]["current_field"] == action_flow.CLARIFY_FIELD
    assert f'"{ambiguous}" es la respuesta o querés hacer otra consulta?' in asked["message"]
    assert question in asked["message"]
    pending = records["pending"]
    assert pending["id"] == before["id"] and pending["action_type"] == action_type
    assert pending["payload"].get(field) is None  # the field is still empty
    assert pending["payload"][action_flow.CLARIFY_KEY] == {"message": ambiguous, "field": field}
    assert records["writes"] == []


def test_es_la_respuesta_uses_the_text_as_written_and_continues(records):
    _ask(records, "registra un bono", "Hoy 50000")
    answer = jarvis_engine.process_message("Es la respuesta")
    assert answer["status"] == "PENDING"
    pending = records["pending"]
    assert pending["payload"]["amount"] == 50000.0
    assert pending["current_field"] == "confirm"
    assert action_flow.CLARIFY_KEY not in pending["payload"]

    # The historical flow to the end: "sí" saves once.
    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK"
    assert [(name, kwargs["amount"]) for name, _, kwargs in records["writes"]] == [("bonus", 50000.0)]
    # No duplicated write: a second "sí" has nothing pending to save.
    jarvis_engine.process_message("sí")
    assert len(records["writes"]) == 1


def test_es_otra_consulta_answers_it_and_keeps_the_pending_action(records):
    _ask(records, "registra un bono", "¿qué tengo?")
    answer = jarvis_engine.process_message("es otra consulta")
    # Answered as a normal request…
    assert "Señor, no tiene compromisos próximos." in answer["message"]
    # …and the pending question survives, intact and reminded.
    assert "Tenés una pregunta pendiente: ¿Cuál es el monto del bono?" in answer["message"]
    assert answer["pending"] is True and answer["pending_action"] == {"action_type": "create_bonus", "current_field": "amount"}
    pending = records["pending"]
    assert pending["action_type"] == "create_bonus" and pending["current_field"] == "amount"
    assert action_flow.CLARIFY_KEY not in pending["payload"] and pending["payload"].get("amount") is None
    assert records["writes"] == []

    # Resumed later with a plain answer…
    resumed = jarvis_engine.process_message("75000")
    assert resumed["status"] == "PENDING" and records["pending"]["payload"]["amount"] == 75000.0


def test_the_kept_action_can_be_cancelled_later(records):
    _ask(records, "registra un bono", "¿qué tengo?", "es otra consulta")
    cancelled = jarvis_engine.process_message("cancelar")
    assert cancelled["status"] == "CANCELLED" and records["pending"] is None
    assert records["writes"] == []


def test_another_request_never_replaces_the_kept_action(records):
    # "Agendá dentista…" is itself a change: answering it as "otra consulta" would start a new
    # pending action and cancel the kept one. JARVIS refuses to, and the bonus stays pending.
    _ask(records, "registra un bono", "Agendá dentista el 11 de octubre", "es otra consulta")
    pending = records["pending"]
    assert pending["action_type"] == "create_bonus" and pending["current_field"] == "amount"
    assert records["writes"] == []


def test_a_plain_answer_goes_on_exactly_as_before(records):
    started = _ask(records, "registra horas extra")
    assert started["status"] == "PENDING"
    answer = jarvis_engine.process_message("3")
    assert answer["data"].get("current_field") != action_flow.CLARIFY_FIELD
    assert "es la respuesta o querés hacer otra consulta" not in answer["message"]
    assert records["pending"]["payload"].get("hours") == 3.0


def test_another_message_during_the_question_goes_to_the_pending_action(records):
    # Neither choice: the question is set aside and the message is handled as usual.
    _ask(records, "registra un bono", "Hoy 50000")
    answer = jarvis_engine.process_message("60000")
    assert answer["status"] == "PENDING" and records["pending"]["payload"]["amount"] == 60000.0


def test_another_workspace_never_sees_the_question(records):
    _ask(records, "registra un bono", "Hoy 50000")
    kept = records["pending"]
    records["pending"] = None  # another account/workspace: its own (empty) pending state
    answer = jarvis_engine.process_message("es la respuesta")
    assert answer.get("action_type") is None and records["writes"] == []
    records["pending"] = kept  # back to the first workspace: untouched
    assert kept["current_field"] == action_flow.CLARIFY_FIELD and kept["payload"][action_flow.CLARIFY_KEY]["message"] == "Hoy 50000"


def test_pending_actions_are_read_and_written_per_workspace(monkeypatch):
    # The real store: every read and update of a pending action is scoped by the session's workspace.
    calls = []

    class Connection:
        def execute(self, sql, params=()):
            calls.append((" ".join(sql.split()), params))
            return self

        def fetchone(self):
            return None

        def commit(self):
            pass

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setattr(chat_memory, "get_connection", connect)
    monkeypatch.setattr(chat_memory, "get_current_workspace_id", lambda: "workspace-a")
    chat_memory.get_pending_action()
    chat_memory.update_pending_action(7, {"name": None}, ["name"], "clarify")
    chat_memory.finish_pending_action(7, "cancelled")
    for sql, params in calls:
        assert "workspace_id = %s" in sql and "workspace-a" in params, sql
