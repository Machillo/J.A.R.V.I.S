"""A payroll receipt email is stored as evidence and linked; it never becomes a transaction."""
from backend.auth.current_user import reset_current_user, set_current_user
from backend.email_monitor import service
from backend.email_monitor.test_payroll_receipt import RECEIPT

WS = "00000000-0000-4000-8000-000000000001"


class _Conn:
    def __enter__(self): return self
    def __exit__(self, *_a): return False
    def commit(self): pass
    def execute(self, query, params=()): raise AssertionError(f"unexpected SQL in this test: {query[:60]}")


def test_a_receipt_email_is_recorded_as_evidence_without_a_candidate_or_transaction(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "get_connection", lambda: _Conn())
    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: WS)
    monkeypatch.setattr(service, "_upsert_ingested_message", lambda conn, **kw: calls.append(("message", kw["status"])) or 1)
    monkeypatch.setattr(service, "_log_email_event", lambda conn, **kw: calls.append(("log", kw["action"])))
    monkeypatch.setattr(service, "_insert_transaction", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create a transaction")))
    monkeypatch.setattr(service.payroll_receipts, "record_receipt",
                        lambda conn, **kw: calls.append(("record", kw["workspace_id"], kw["parsed"]["net"], kw["source"])) or {"status": "RECORDED", "match_status": "PAYROLL_ONLY"})
    token = set_current_user({"id": 7, "account_id": "a", "workspace_id": WS, "role": "owner"})
    try:
        result = service.scan_email_text(subject="Recibo de pago", sender="payroll@empresa-ejemplo.test", body=RECEIPT, provider_message_id="msg-1")
    finally:
        reset_current_user(token)
    assert result["status"] == "PAYROLL_RECEIPT" and result["candidate"] is None
    assert ("message", "payroll_receipt") in calls and ("log", "payroll_receipt") in calls
    assert ("record", WS, 56558.75, "mail_receipt") in calls


def test_a_saved_income_tries_the_receipts_waiting_for_their_deposit(monkeypatch):
    seen = []
    monkeypatch.setattr(service, "_workspace_id_for_user", lambda conn, user_id: WS)
    monkeypatch.setattr(service.payroll_receipts, "match_pending_for_transaction",
                        lambda conn, **kw: seen.append((kw["workspace_id"], kw["transaction_id"])) or [])

    class Conn:
        def execute(self, query, params=()):
            return type("R", (), {"fetchone": lambda self: None, "fetchall": lambda self: []})()

    service._match_payroll_receipts(Conn(), 7, 99)
    assert seen == [(WS, 99)]
