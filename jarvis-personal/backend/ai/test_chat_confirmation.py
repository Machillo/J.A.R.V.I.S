"""JARVIS chat (J1): a change the chat understands is shown first and saved only on "sí".

The chat keeps its historical interpretation (OT, extra hours, holidays, VGH and bonuses in plain
words; calendar, memory and fixed expenses) and its historical replies. What changed: it no longer
saves those messages at once. The pending change lives in chat_pending_actions, like every other
chat action, stubbed here in memory. Nothing touches a database.
"""
from __future__ import annotations

import pytest

from backend.ai import action_flow, jarvis_engine
from backend.ai import strategy_dashboard
from backend.finance import fixed_expenses
from backend.finance import service as finance_service

PROFILE = {"hourly_rate": 2000.0, "overtime_multiplier": 1.5, "holiday_multiplier": 2.0}


@pytest.fixture
def chat(monkeypatch):
    """The engine with an in-memory pending action and recorded writes."""
    state = {"pending": None, "writes": []}

    def create_pending_action(action_type, payload, missing, current_field):
        state["pending"] = {"id": 1, "action_type": action_type, "payload": dict(payload),
                            "missing_fields": list(missing), "current_field": current_field}
        return dict(state["pending"])

    def update_pending_action(action_id, payload, missing, current_field):
        state["pending"].update(payload=dict(payload), missing_fields=list(missing), current_field=current_field)

    def finish_pending_action(action_id, status="completed"):
        state["pending"] = None

    for module in (action_flow, jarvis_engine):
        monkeypatch.setattr(module, "get_pending_action", lambda: state["pending"], raising=False)
        monkeypatch.setattr(module, "finish_pending_action", finish_pending_action, raising=False)
    monkeypatch.setattr(action_flow, "create_pending_action", create_pending_action)
    monkeypatch.setattr(action_flow, "update_pending_action", update_pending_action)
    monkeypatch.setattr(jarvis_engine, "handle_personal_decision_request", lambda message: None)
    monkeypatch.setattr(finance_service, "get_employment_profile", lambda: dict(PROFILE))
    monkeypatch.setattr(strategy_dashboard, "build_local_strategy_blueprint",
                        lambda: {"monthly_income": 900000, "estimated_extra_cash": 120000})

    def record(name, result):
        def write(*args, **kwargs):
            state["writes"].append((name, args, kwargs))
            return result
        return write

    monkeypatch.setattr(action_flow, "add_payroll_event", record("payroll_event", {"status": "OK"}))
    monkeypatch.setattr(action_flow, "add_bonus", record("bonus", {"id": 9}))
    monkeypatch.setattr(action_flow, "add_event", record("event", {"id": 7}))
    monkeypatch.setattr(action_flow, "create_memory_item", record("memory", {"id": 5}))
    monkeypatch.setattr(fixed_expenses, "create_fixed_expense", record("fixed_create", {"id": 3, "name": "internet"}))
    monkeypatch.setattr(fixed_expenses, "update_fixed_expense", record("fixed_update", {"id": 4, "name": "agua"}))
    monkeypatch.setattr(fixed_expenses, "list_fixed_expenses", lambda active_only=True: [{"id": 4, "name": "agua", "aliases": []}])
    return state


@pytest.mark.parametrize("message, event_type, hours, amount", [
    ("Hoy hice 3 horas de OT", "ot", 3.0, "₡9,000.00"),          # 3 h × 2000 × 1.5
    ("Hoy hice 2 horas extra", "ot", 2.0, "₡6,000.00"),
    ("Hoy hice 8 horas de feriado", "holiday", 8.0, "₡32,000.00"),  # 8 h × 2000 × 2
    ("VGH de 4 horas", "vgh", 4.0, "₡-8,000.00"),                 # unpaid: −1 × 4 h × 2000
])
def test_payroll_messages_show_the_computed_amount_and_save_only_on_yes(chat, message, event_type, hours, amount):
    first = jarvis_engine.process_message(message)
    assert first["status"] == "PENDING" and first["pending"] is True
    assert first["action_type"] == "create_payroll_event"
    assert amount in first["message"] and "¿Confirmo y guardo?" in first["message"]
    assert chat["writes"] == []  # nothing is saved before the confirmation

    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK" and saved["pending"] is False
    assert [(name, kwargs["event_type"], kwargs["hours"]) for name, _, kwargs in chat["writes"]] == [("payroll_event", event_type, hours)]
    # The historical reply, with the recomputed projection.
    assert "registrado" in saved["message"] and "Ingreso proyectado actualizado" in saved["message"]


def test_the_preview_and_the_saved_event_use_the_same_formula():
    for event_type, hours in [("ot", 3.0), ("holiday", 8.0), ("vgh", 4.0), ("other", 5.0)]:
        multiplier, amount = finance_service.payroll_event_amount(PROFILE, event_type, hours)
        expected = {"ot": 1.5, "holiday": 2.0, "vgh": -1, "other": 1}[event_type]
        assert (multiplier, amount) == (expected, hours * 2000.0 * expected)


def test_a_bonus_is_confirmed_before_saving_and_no_cancels_it(chat):
    first = jarvis_engine.process_message("Hoy me llegó 50000 de bono")
    assert first["status"] == "PENDING" and "₡50,000.00" in first["message"]
    cancelled = jarvis_engine.process_message("no")
    assert cancelled["status"] == "CANCELLED" and chat["writes"] == [] and chat["pending"] is None

    jarvis_engine.process_message("Hoy me llegó un bono de 75 mil")
    saved = jarvis_engine.process_message("sí")
    assert [(name, kwargs["amount"]) for name, _, kwargs in chat["writes"]] == [("bonus", 75000.0)]
    assert "bono registrado por ₡75.000" in saved["message"]


def test_payroll_without_an_employment_profile_is_refused_not_announced(chat, monkeypatch):
    # Before J1 the chat said "registrado" while add_payroll_event refused to save.
    monkeypatch.setattr(finance_service, "get_employment_profile", lambda: None)
    answer = jarvis_engine.process_message("Hoy hice 3 horas de OT")
    assert answer["status"] == "ERROR" and answer["pending"] is False
    assert "perfil laboral" in answer["message"]
    assert chat["writes"] == [] and chat["pending"] is None


def test_calendar_memory_and_fixed_expenses_wait_for_yes(chat):
    cases = [
        ("Agendá cita con el dentista el 5 de octubre a las 3pm", "create_calendar_event", "event", "Guardé en calendario"),
        ("Recordá que el gimnasio cierra a las 8", "create_memory", "memory", "Listo, lo recordaré."),
        ("Agrega gasto fijo internet 25000 día 5", "create_fixed_expense", "fixed_create", "como gasto fijo"),
        ("Actualiza el gasto fijo del agua a 27000", "update_fixed_expense", "fixed_update", "Actualicé agua"),
    ]
    for message, action_type, write, reply in cases:
        chat["writes"].clear()
        first = jarvis_engine.process_message(message)
        assert first["status"] == "PENDING" and first["action_type"] == action_type, message
        assert chat["writes"] == [], message
        assert "fixed_expense_id" not in first["message"]  # internal ids are never shown
        saved = jarvis_engine.process_message("sí")
        assert [name for name, _, _ in chat["writes"]] == [write], message
        assert reply in saved["message"], message


def test_a_calendar_message_without_a_date_still_asks_for_it(chat):
    answer = jarvis_engine.process_message("Agendá una reunión con el contador")
    assert answer["status"] == "NEEDS_DATE" and answer["pending"] is False
    assert chat["writes"] == [] and chat["pending"] is None
