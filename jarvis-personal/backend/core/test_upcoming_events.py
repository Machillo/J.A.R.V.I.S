"""The Owner's agenda (J2): upcoming events from the historical `events` table, the same ones the
JARVIS chat answers "¿qué tengo?" with, and the ones a confirmed chat event adds.

An in-memory `events` table stands behind get_connection (INSERT from add_event, SELECT scoped by
workspace); the chat's pending action is stubbed in memory. Nothing touches a database.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date, timedelta

import pytest

from backend.ai import action_flow, jarvis_engine
from backend.core import events as events_module
from backend.tasks import calendar_service

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


class EventsTable:
    """Answers the two statements core/events sends: INSERT one event, SELECT a workspace's events."""

    def __init__(self):
        self.rows: list[dict] = []
        self.workspace = "workspace-a"
        self.selects: list[tuple] = []

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        if text.startswith("INSERT INTO events"):
            title, description, event_type, event_date, workspace_id = params
            self.rows.append({"id": len(self.rows) + 1, "title": title, "description": description, "event_type": event_type,
                              "event_date": event_date, "user_id": None, "workspace_id": workspace_id, "created_at": None})
            self.lastrowid = len(self.rows)
            return self
        assert "FROM events" in text and "WHERE workspace_id = %s" in text, text
        self.selects.append(params)
        prefix = re.compile(r"^\d{4}-\d{2}-\d{2}")
        self.result = [dict(row) for row in self.rows
                       if row["workspace_id"] == params[0] and str(row["event_date"] or "").strip() and prefix.match(str(row["event_date"]).strip())]
        return self

    def fetchall(self):
        return self.result

    def commit(self):
        pass


@pytest.fixture
def table(monkeypatch):
    db = EventsTable()

    @contextmanager
    def connect():
        yield db

    monkeypatch.setattr(events_module, "get_connection", connect)
    monkeypatch.setattr(events_module, "get_current_workspace_id", lambda: db.workspace)
    monkeypatch.setattr(events_module, "get_current_user_id", lambda: None)
    return db


def add(db, event_date, title, workspace="workspace-a"):
    db.rows.append({"id": len(db.rows) + 1, "title": title, "description": "", "event_type": "personal", "event_date": event_date,
                    "user_id": None, "workspace_id": workspace, "created_at": None})


TODAY = date(2026, 9, 30)


def test_past_events_never_appear_and_today_and_the_next_45_days_do(table):
    add(table, "2026-09-29 18:00", "Ayer")
    add(table, "2026-01-05 09:00", "Hace meses")
    add(table, "2026-09-30 08:00", "Hoy temprano")      # today counts, whatever the hour (historical semantics)
    add(table, "2026-11-14 10:00", "Día 45")
    add(table, "2026-11-15 10:00", "Día 46")
    titles = [event["title"] for event in events_module.get_upcoming_events(45, today=TODAY)]
    assert titles == ["Hoy temprano", "Día 45"]


def test_upcoming_events_are_in_chronological_order(table):
    add(table, "2026-10-20 09:00", "Tercero")
    add(table, "2026-10-02 16:30", "Segundo")
    add(table, "2026-10-02 08:15", "Primero")
    add(table, "2026-10-21", "Cuarto (sin hora)")
    titles = [event["title"] for event in events_module.get_upcoming_events(45, today=TODAY)]
    assert titles == ["Primero", "Segundo", "Tercero", "Cuarto (sin hora)"]


def test_malformed_or_legacy_dates_are_skipped_never_guessed(table):
    # Before J2 the SQL cast "2026-02-30" to a date and the whole agenda failed.
    add(table, "2026-02-30 10:00", "Fecha imposible")
    add(table, "2026-10-32", "Día 32")
    add(table, "10/10/2026", "Formato viejo")
    add(table, "", "Vacío")
    add(table, "mañana", "Texto")
    add(table, "2026-10-05 11:00", "Válido")
    assert [event["title"] for event in events_module.get_upcoming_events(45, today=TODAY)] == ["Válido"]
    assert events_module.event_day("2026-02-30 10:00") is None
    assert events_module.event_day("2026-10-05 11:00") == date(2026, 10, 5)
    # Nothing stored was changed.
    assert [row["event_date"] for row in table.rows][:5] == ["2026-02-30 10:00", "2026-10-32", "10/10/2026", "", "mañana"]


def test_each_workspace_sees_only_its_events(table):
    add(table, "2026-10-05 11:00", "Mío")
    add(table, "2026-10-05 11:00", "De otra cuenta", workspace="workspace-b")
    assert [event["title"] for event in events_module.get_upcoming_events(45, today=TODAY)] == ["Mío"]
    assert table.selects[-1] == ("workspace-a",)
    table.workspace = "workspace-b"
    assert [event["title"] for event in events_module.get_upcoming_events(45, today=TODAY)] == ["De otra cuenta"]


def test_que_tengo_answers_with_the_agendas_upcoming_events(table):
    today = date.today()
    add(table, (today - timedelta(days=3)).isoformat() + " 10:00", "Pasado")
    add(table, (today + timedelta(days=9)).isoformat() + " 10:00", "Después")
    add(table, (today + timedelta(days=2)).isoformat() + " 10:00", "Pronto")
    add(table, (today + timedelta(days=60)).isoformat() + " 10:00", "Lejano")
    summary = calendar_service.calendar_summary()
    assert [event["title"] for event in summary["events"]] == ["Pronto", "Después"]
    assert summary["message"] == "Señor, estos son sus próximos compromisos."
    assert [event["title"] for event in summary["events"]] == [event["title"] for event in events_module.get_upcoming_events(events_module.AGENDA_DAYS)]


def test_que_tengo_without_upcoming_events_says_so(table):
    add(table, (date.today() - timedelta(days=1)).isoformat() + " 10:00", "Pasado")
    summary = calendar_service.calendar_summary()
    assert summary["events"] == [] and summary["message"] == "Señor, no tiene compromisos próximos."


@pytest.fixture
def chat_pending(monkeypatch):
    state = {"pending": None}

    def create_pending_action(action_type, payload, missing, current_field):
        state["pending"] = {"id": 1, "action_type": action_type, "payload": dict(payload), "missing_fields": list(missing), "current_field": current_field}
        return dict(state["pending"])

    def finish_pending_action(action_id, status="completed"):
        state["pending"] = None

    for module in (action_flow, jarvis_engine):
        monkeypatch.setattr(module, "get_pending_action", lambda: state["pending"], raising=False)
        monkeypatch.setattr(module, "finish_pending_action", finish_pending_action, raising=False)
    monkeypatch.setattr(action_flow, "create_pending_action", create_pending_action)
    monkeypatch.setattr(action_flow, "update_pending_action", lambda *args: None)
    monkeypatch.setattr(jarvis_engine, "handle_personal_decision_request", lambda message: None)
    return state


def test_a_chat_event_reaches_the_agenda_only_once_confirmed(table, chat_pending):
    day = date.today() + timedelta(days=10)
    message = f"Agendá dentista el {day.day} de {MONTHS[day.month - 1]} a las 3pm"
    asked = jarvis_engine.process_message(message)
    assert asked["status"] == "PENDING" and asked["action_type"] == "create_calendar_event"
    assert events_module.get_upcoming_events(events_module.AGENDA_DAYS) == []  # not before "sí"

    saved = jarvis_engine.process_message("sí")
    assert saved["status"] == "OK"
    agenda = events_module.get_upcoming_events(events_module.AGENDA_DAYS)
    assert [(event["title"], event["event_date"], event["event_type"]) for event in agenda] == [("dentista", f"{day.isoformat()} 15:00", "personal")]
    # And the chat's "¿qué tengo?" sees the same event.
    assert "dentista" in jarvis_engine.process_message("qué tengo en mi agenda")["message"]
