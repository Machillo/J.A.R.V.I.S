from datetime import date

import pytest
from fastapi import HTTPException

from backend.user_product import own_transfer_review as transfers


def _candidate(candidate_id, direction, **changes):
    row = {
        "id": candidate_id, "email_message_id": candidate_id + 100,
        "bank": "bac" if direction == "out" else "multimoney",
        "transaction_date": date(2026, 9, 22), "transaction_time": None,
        "amount": "10000.00", "currency": "CRC", "movement_kind": "transfer",
        "movement_direction": direction, "external_reference": f"unrelated-{candidate_id}",
        "transaction_id": None, "status": "pending", "is_internal_transfer": False,
    }
    row.update(changes)
    return row


class _Result:
    def __init__(self, rows=None, one=None):
        self.rows, self.one = rows or [], one

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class _Connection:
    def __init__(self, rows, linked=None):
        self.rows, self.linked, self.calls, self.committed = rows, linked, [], False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))
        if "FROM finva_email_candidates" in query:
            return _Result(rows=self.rows)
        if "FROM transactions" in query:
            return _Result(one=self.linked)
        return _Result()

    def commit(self):
        self.committed = True


def _identity(monkeypatch, conn):
    monkeypatch.setattr(transfers, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(transfers, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(transfers, "get_connection", lambda: conn)


def test_different_bank_references_can_be_suggested_but_not_auto_saved(monkeypatch):
    conn = _Connection([_candidate(1, "out"), _candidate(2, "in")])
    _identity(monkeypatch, conn)
    proposals = transfers.list_own_transfer_suggestions()
    assert len(proposals["items"]) == 1
    assert proposals["items"][0]["first"]["reference_end"] == "ted1"
    assert conn.calls[0][1] == ("account-a", "workspace-a")
    assert "account_id=%s AND workspace_id=%s" in conn.calls[0][0]
    assert not conn.committed


@pytest.mark.parametrize("change", [
    {"amount": "10001.00"}, {"currency": "USD"},
    {"transaction_date": date(2026, 9, 23)},
    {"movement_direction": "out"}, {"movement_kind": "card_purchase"},
    {"email_message_id": 101}, {"is_internal_transfer": True},
    {"transaction_time": "23:00:00"},
])
def test_unrelated_notices_are_not_paired(change):
    first = _candidate(1, "out", transaction_time="08:00:00")
    assert not transfers._eligible(first, _candidate(2, "in", **change))


def test_unknown_direction_requires_explicit_opposite_choice():
    first, second = _candidate(1, "out"), _candidate(2, "unknown")
    assert transfers._eligible(first, second)
    assert not transfers._eligible(first, second, "out")
    assert transfers._eligible(first, second, "in")
    assert not transfers._eligible(first, _candidate(2, "unknown", movement_direction="unknown"), "out")


def test_confirm_marks_both_notices_without_creating_or_deleting_transactions(monkeypatch):
    conn = _Connection([_candidate(1, "out"), _candidate(2, "in")])
    _identity(monkeypatch, conn)
    result = transfers.confirm_own_transfer(1, 2)
    assert result["excluded_from_income_expenses"]
    assert len([query for query, _ in conn.calls if "UPDATE finva_email_candidates" in query]) == 2
    assert not any("UPDATE transactions" in query for query, _ in conn.calls)
    assert not any("DELETE" in query or "INSERT" in query for query, _ in conn.calls)
    assert conn.committed


def test_confirm_reclassifies_saved_transactions_and_events(monkeypatch):
    conn = _Connection([_candidate(1, "out", status="confirmed", transaction_id=19),
                        _candidate(2, "in", status="confirmed", transaction_id=20)],
                       linked={"id": 19, "transaction_type": "expense"})
    _identity(monkeypatch, conn)
    transfers.confirm_own_transfer(1, 2)
    assert len([q for q, _ in conn.calls if "UPDATE transactions" in q]) == 2
    assert len([q for q, _ in conn.calls if "UPDATE financial_input_events" in q]) == 2
    assert all("workspace_id=%s" in q for q, _ in conn.calls)
    assert conn.committed


def test_missing_linked_transaction_blocks_both_updates(monkeypatch):
    conn = _Connection([_candidate(1, "out", transaction_id=19), _candidate(2, "in")])
    _identity(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        transfers.confirm_own_transfer(1, 2)
    assert exc.value.status_code == 409
    assert not conn.committed
    assert not any("UPDATE " in q for q, _ in conn.calls)


def test_missing_account_scoped_counterpart_is_rejected(monkeypatch):
    conn = _Connection([_candidate(1, "out")])
    _identity(monkeypatch, conn)
    with pytest.raises(HTTPException) as exc:
        transfers.confirm_own_transfer(1, 2)
    assert exc.value.status_code == 404
    assert conn.calls[0][1] == ("account-a", "workspace-a", 1, 2)


def test_unknown_direction_confirmation_must_be_opposite(monkeypatch):
    conn = _Connection([_candidate(1, "out"), _candidate(2, "unknown")])
    _identity(monkeypatch, conn)
    with pytest.raises(HTTPException):
        transfers.confirm_own_transfer(1, 2, "out")
    assert not conn.committed
    assert transfers.confirm_own_transfer(1, 2, "in")["status"] == "confirmed"
