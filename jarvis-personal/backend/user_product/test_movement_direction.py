"""finva_candidates_direction_check: one canonical direction, and one bad message never stops a sync.

Production (2026-09-25): a MultiMoney "Recibimos tu pago" notice produced the
direction 'payment'. The candidate column was normalized, but raw_payload kept
'payment' and the resolution wrote it back into movement_direction, so the
CHECK rejected the whole message transaction (the movement was silently lost,
and every Gmail sync failed on the same message).
"""
import re
from datetime import date
from pathlib import Path

import pytest

from backend.email_monitor import parser as p
from backend.user_product import gmail_service
from backend.user_product.candidate_resolution import resolve_candidate
from backend.user_product.financial_candidate import canonical_candidate
from backend.user_product.movement_direction import DIRECTIONS, canonical_direction

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "20260921170000_phase_1b_canonical_financial_candidates.sql"
MULTIMONEY = "MultiMoney <avisos@multimoney.com>"
PAYMENT_RECEIVED = (
    "MultiMoney\nRecibimos tu pago\nMonto: CRC 25.000\nFecha: 22/09/2026\n"
    "Referencia: 555000111\nConcepto: pago tarjeta"
)


def test_the_canonical_directions_are_exactly_the_database_check():
    sql = MIGRATION.read_text(encoding="utf-8")
    check = re.search(r"finva_candidates_direction_check\s+CHECK \(movement_direction IN \(([^)]*)\)\)", sql)
    assert check, "the CHECK moved: keep DIRECTIONS and the constraint in sync"
    assert tuple(value.strip().strip("'") for value in check.group(1).split(",")) == DIRECTIONS


@pytest.mark.parametrize(("value", "transaction_type", "expected"), [
    ("in", None, "in"), (" OUT ", None, "out"), ("internal", None, "internal"),
    ("payment", None, "unknown"), ("payment", "debt_payment", "out"), ("credit", "income", "in"),
    (None, "expense", "out"), ("", None, "unknown"), (3, None, "unknown"), ("unknown", "transfer", "unknown"),
])
def test_every_value_maps_into_the_domain(value, transaction_type, expected):
    assert canonical_direction(value, transaction_type) == expected


def test_the_parser_vocabulary_is_left_alone_for_the_owner_flow():
    """The Owner's private flow keys rules and dedupe on the parser's own 'payment'
    (production: rules and stored keys use it). The canonical boundary is where a
    candidate enters finva_email_candidates, not the shared parser."""
    parsed = p._parse_multimoney_transfer("Notificación de transferencia", MULTIMONEY, PAYMENT_RECEIVED, "2026-09-22T10:00:00Z")
    assert parsed["transaction_type"] == "debt_payment" and parsed["movement_direction"] == "payment"


@pytest.mark.parametrize("line", [
    "Se aplico un debito en tiempo real", "Se aplico un credito en tiempo real", "Recibimos tu pago",
    "Recepción de fondos", "Movimiento sin clasificar",
])
def test_every_multimoney_branch_becomes_a_canonical_candidate(line):
    body = f"MultiMoney\n{line}\nMonto: CRC 10.000\nFecha: 22/09/2026\nReferencia: 1\nConcepto: prueba"
    parsed = p._parse_multimoney_transfer("Notificación de transferencia", MULTIMONEY, body, "2026-09-22T10:00:00Z")
    candidate = canonical_candidate(parsed, provider_message_id="m-1", subject="Aviso")
    assert candidate["movement_direction"] in DIRECTIONS
    assert candidate["raw_payload"]["movement_direction"] in DIRECTIONS


def test_a_multimoney_payment_received_becomes_money_out():
    parsed = p._parse_multimoney_transfer("Notificación de transferencia", MULTIMONEY, PAYMENT_RECEIVED, "2026-09-22T10:00:00Z")
    candidate = canonical_candidate(parsed, provider_message_id="m-1", subject="Aviso")
    assert (candidate["transaction_type"], candidate["movement_direction"]) == ("debt_payment", "out")
    assert candidate["raw_payload"]["movement_direction"] == "out"


def test_the_candidate_and_its_raw_payload_carry_the_canonical_direction():
    """raw_payload is what the resolution writes back: it must already be canonical."""
    candidate = canonical_candidate({"transaction_type": "debt_payment", "movement_direction": "payment", "amount": 1},
                                    provider_message_id="m-1", subject="Aviso")
    assert candidate["movement_direction"] == "out"
    assert candidate["raw_payload"]["movement_direction"] == "out"


class _Result:
    def __init__(self, one=None, rows=None):
        self.one, self.rows = one, rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, results):
        self.results, self.calls = iter(results), []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return next(self.results)


def test_resolving_a_legacy_raw_direction_never_writes_it_back():
    """A candidate stored before the fix (raw 'payment') resolves to a direction the CHECK accepts."""
    legacy = {
        "id": 9, "account_id": "account-a", "workspace_id": "workspace-a",
        "transaction_date": date(2026, 9, 22), "transaction_time": None, "description": "Pago recibido MultiMoney",
        "amount": 25000, "currency": "CRC", "bank": "multimoney", "external_reference": None,
        "source_account_reference": None, "destination_account_reference": None, "movement_kind": "other",
        "transaction_type": "debt_payment", "movement_direction": "unknown",
        "raw_payload": {"transaction_type": "debt_payment", "movement_direction": "payment", "category": "MultiMoney"},
    }
    connection = _Connection([_Result(one=legacy), _Result(one=None), _Result(rows=[]), _Result(), _Result(), _Result()])
    assert resolve_candidate(connection, 9) == {"status": "pending"}
    query, params = connection.calls[-1]
    assert "movement_direction=CASE WHEN %s THEN 'internal' ELSE %s END" in query
    assert params[5] == "out" and params[5] in DIRECTIONS


CONNECTION = {"id": 3, "account_id": "account-a", "workspace_id": "workspace-a", "legacy_user_id": 1, "display_name": ""}


def test_a_message_that_cannot_be_stored_is_recorded_and_the_batch_continues(monkeypatch):
    recorded = []

    class _Recorder:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=()):
            recorded.append((" ".join(query.split()), params))
            return _Result(one={"id": 1})

        def commit(self):
            recorded.append(("COMMIT", ()))

    def ingest_once(_connection, message_id, **_kwargs):
        if message_id == "poison":
            raise RuntimeError("new row violates check constraint")
        return "pending"

    monkeypatch.setattr(gmail_service, "_ingest_message_once", ingest_once)
    monkeypatch.setattr(gmail_service, "get_connection", _Recorder)
    results = [gmail_service._ingest_message(CONNECTION, message_id, subject="Aviso", sender="x@y", body="")
               for message_id in ("first", "poison", "last")]
    assert results == ["pending", "failed", "pending"]
    insert, params = recorded[0]
    assert insert.startswith("INSERT INTO finva_email_messages") and "'failed'" in insert
    assert "WHERE finva_email_messages.status='failed'" in insert  # never overwrites a processed message
    assert params[3] == "poison" and recorded[1] == ("COMMIT", ())


@pytest.mark.parametrize("transient", ["operational", "deadlock", "lock_timeout", "permission"])
def test_a_transient_failure_stops_the_batch_and_keeps_the_cursor(monkeypatch, transient):
    """A timeout, deadlock or dropped connection is not the message's fault: nothing is
    recorded as failed and the sync stops, so the same page is read again next time."""
    import psycopg2

    class _Deadlock(Exception):
        pgcode = "40P01"

    class _LockTimeout(Exception):
        pgcode = "55P03"

    class _Permission(Exception):
        pgcode = "42501"  # a missing grant of the application role

    error = {"operational": psycopg2.OperationalError("server closed the connection"),
             "deadlock": _Deadlock(), "lock_timeout": _LockTimeout(), "permission": _Permission()}[transient]

    def ingest_once(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(gmail_service, "_ingest_message_once", ingest_once)
    monkeypatch.setattr(gmail_service, "get_connection", lambda: pytest.fail("a transient failure must not be recorded"))
    with pytest.raises(type(error)):
        gmail_service._ingest_message(CONNECTION, "m-1", subject="Aviso", sender="x@y", body="")


def test_failed_messages_are_counted_in_the_sync_result_and_analytics():
    from backend.product_ops.posthog_events import safe_server_properties

    assert safe_server_properties("mail_sync_completed", {"messages_failed": 2}).get("messages_failed") == 2
    for module in (gmail_service, __import__("backend.user_product.microsoft_mail", fromlist=["x"])):
        assert '"failed": results.count("failed")' in Path(module.__file__).read_text(encoding="utf-8")


def test_a_failed_message_is_processed_again_instead_of_skipped_as_duplicate(monkeypatch):
    connection = _Connection([_Result(one={"id": 5, "status": "failed"}), _Result(), _Result()])

    class _Scope:
        def __enter__(self):
            return connection

        def __exit__(self, *_args):
            return False

    connection.commit = lambda: None
    monkeypatch.setattr(gmail_service, "get_connection", _Scope)
    status = gmail_service._ingest_message_once(CONNECTION, "gmail-5", subject="Hola", sender="amigo@example.com", body="hola")
    assert status != "duplicate"
    assert connection.calls[1][0].startswith("UPDATE finva_email_messages SET bank=%s,status=%s,parse_reason=%s WHERE id=%s")
