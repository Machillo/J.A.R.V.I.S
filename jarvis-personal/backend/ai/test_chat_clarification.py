"""JARVIS chat (J1): a pending question is never answered, or cancelled, by a message that is also
another request. JARVIS asks: "es la respuesta" uses the text as written, "es otra consulta" answers
it as a normal request and keeps the pending action where it was. Messages the flow always took
(`general` answers, numbers, yes/no) go on exactly as before. In-memory stubs only (the `chat`
fixture of test_chat_confirmation); nothing touches a database.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from backend.ai import action_flow, chat_memory, jarvis_engine
from backend.ai.test_chat_confirmation import chat  # noqa: F401  (the shared in-memory chat)


@pytest.fixture
def records(chat, monkeypatch):  # noqa: F811
    """The creates these flows end with, recorded instead of saved."""
    def record(name):
        def write(**kwargs):
            chat["writes"].append((name, (), kwargs))
            return {"id": 1, **kwargs}
        return write

    monkeypatch.setattr(action_flow, "add_financial_goal", record("goal"))
    monkeypatch.setattr(action_flow, "add_debt", record("debt"))
    monkeypatch.setattr(jarvis_engine, "get_financial_engine_report", lambda: {"status": "OK"})
    monkeypatch.setattr(jarvis_engine, "_format_financial_engine_message", lambda report: "Señor, este es su análisis financiero.")
    return chat


def _ask(chat, *messages):
    answer = None
    for message in messages:
        answer = jarvis_engine.process_message(message)
    return answer


@pytest.mark.parametrize("opening, question, ambiguous, field, action_type", [
    ("quiero crear una meta", "¿Cómo se llama la meta?", "Fondo de emergencia", "name", "create_goal"),
    ("agrega una deuda", "¿Cómo se llama la deuda?", "Deuda con Juan", "name", "create_debt"),
    ("importar estado de cuenta", "¿Qué mes vamos a importar?", "septiembre", "month", "import_monthly_statement"),
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
    _ask(records, "quiero crear una meta", "Fondo de emergencia")
    answer = jarvis_engine.process_message("Es la respuesta")
    assert answer["status"] == "PENDING"
    assert "¿Cuál es el monto objetivo de la meta?" in answer["message"]
    pending = records["pending"]
    assert pending["payload"]["name"] == "Fondo de emergencia"
    assert pending["current_field"] == "target_amount"
    assert action_flow.CLARIFY_KEY not in pending["payload"]

    # The historical flow to the end: amount, summary, "sí" saves once.
    jarvis_engine.process_message("600000")
    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK"
    assert [(name, kwargs["name"], kwargs["target_amount"]) for name, _, kwargs in records["writes"]] == [("goal", "Fondo de emergencia", 600000.0)]
    # No duplicated write: a second "sí" has nothing pending to save.
    jarvis_engine.process_message("sí")
    assert len(records["writes"]) == 1


def test_deuda_con_juan_can_be_the_debt_name(records):
    _ask(records, "agrega una deuda", "Deuda con Juan", "es la respuesta")
    assert records["pending"]["payload"]["name"] == "Deuda con Juan"
    assert records["pending"]["current_field"] == "total_amount"


def test_septiembre_can_be_the_month_to_import(records):
    _ask(records, "importar estado de cuenta", "septiembre", "es la respuesta")
    pending = records["pending"]
    assert pending["action_type"] == "import_monthly_statement"
    assert pending["payload"].get("month") and pending["current_field"] != action_flow.CLARIFY_FIELD
    assert records["writes"] == []


def test_es_otra_consulta_answers_it_and_keeps_the_pending_action(records):
    _ask(records, "quiero crear una meta", "Fondo de emergencia")
    answer = jarvis_engine.process_message("es otra consulta")
    # Answered as a normal request…
    assert "Señor, este es su análisis financiero." in answer["message"]
    # …and the pending question survives, intact and reminded.
    assert "Tenés una pregunta pendiente: ¿Cómo se llama la meta?" in answer["message"]
    assert answer["pending"] is True and answer["pending_action"] == {"action_type": "create_goal", "current_field": "name"}
    pending = records["pending"]
    assert pending["action_type"] == "create_goal" and pending["current_field"] == "name"
    assert action_flow.CLARIFY_KEY not in pending["payload"] and pending["payload"].get("name") is None
    assert records["writes"] == []

    # Resumed later with a plain answer…
    resumed = jarvis_engine.process_message("Metas del año")
    assert resumed["status"] == "PENDING" and records["pending"]["payload"]["name"] == "Metas del año"


def test_the_kept_action_can_be_cancelled_later(records):
    _ask(records, "quiero crear una meta", "Fondo de emergencia", "es otra consulta")
    cancelled = jarvis_engine.process_message("cancelar")
    assert cancelled["status"] == "CANCELLED" and records["pending"] is None
    assert records["writes"] == []


def test_another_request_never_replaces_the_kept_action(records):
    # "Agrega gasto fijo…" is itself a change: answering it as "otra consulta" would start a new
    # pending action and cancel the kept one. JARVIS refuses to, and the goal stays pending.
    _ask(records, "quiero crear una meta", "Agrega gasto fijo internet 25000", "es otra consulta")
    pending = records["pending"]
    assert pending["action_type"] == "create_goal" and pending["current_field"] == "name"
    assert records["writes"] == []


def test_a_general_answer_goes_on_exactly_as_before(records):
    started = _ask(records, "registra un gasto")
    assert started["status"] == "PENDING"
    answer = jarvis_engine.process_message("Comida")
    assert answer["data"].get("current_field") != action_flow.CLARIFY_FIELD
    assert "es la respuesta o querés hacer otra consulta" not in answer["message"]
    assert records["pending"]["payload"].get("category") == "Comida"


def test_another_message_during_the_question_goes_to_the_pending_action(records):
    # Neither choice: the question is set aside and the message is handled as usual.
    _ask(records, "quiero crear una meta", "Fondo de emergencia")
    answer = jarvis_engine.process_message("Metas del año")
    assert answer["status"] == "PENDING" and records["pending"]["payload"]["name"] == "Metas del año"


def test_another_workspace_never_sees_the_question(records):
    _ask(records, "quiero crear una meta", "Fondo de emergencia")
    kept = records["pending"]
    records["pending"] = None  # another account/workspace: its own (empty) pending state
    answer = jarvis_engine.process_message("es la respuesta")
    assert answer.get("action_type") is None and records["writes"] == []
    records["pending"] = kept  # back to the first workspace: untouched
    assert kept["current_field"] == action_flow.CLARIFY_FIELD and kept["payload"][action_flow.CLARIFY_KEY]["message"] == "Fondo de emergencia"


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
