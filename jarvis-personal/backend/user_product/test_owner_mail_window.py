"""The Owner's mailbox syncs read only the current month and run no history scan; Users keep theirs.

The Owner's January–September ledger is recorded or reconstructed outside mail; reading the
year's history again would offer those months as new candidates. Only a verified Owner
connection (stored records) gets the Owner window and the learned-rule save; a DINCR User's
connection keeps the chosen history scan and confirms every movement. Synthetic data only.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.user_product import gmail_service, owner_mail_automation
from backend.user_product import microsoft_mail as ms

OCT_1, TODAY = date(2026, 10, 1), date(2026, 10, 19)


def test_the_owner_window_is_the_current_month_never_before_the_chosen_date():
    assert owner_mail_automation.window_since({}, date(2026, 1, 1), TODAY) == OCT_1
    assert owner_mail_automation.window_since({}, date(2026, 10, 10), TODAY) == date(2026, 10, 10)
    assert owner_mail_automation.window_since({}, date(2026, 1, 1), date(2026, 11, 1)) == date(2026, 11, 1)


class _Db:
    def __init__(self, answers=None):
        self.calls, self.answers, self.committed = [], answers or {}, False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        flat = " ".join(query.split())
        self.calls.append((flat, params))
        one = next((value for key, value in self.answers.items() if flat.startswith(key)), None)
        return SimpleNamespace(fetchone=lambda: one, fetchall=lambda: [])

    def commit(self):
        self.committed = True


PENDING_HISTORY = {"id": 12, "account_id": "account-o", "workspace_id": "workspace-o", "import_scope": "current_year",
                   "import_since": date(2026, 1, 1), "initial_scan_completed_at": None, "initial_scan_page_token": "page-4"}


def _gmail_sync(monkeypatch, *, owner):
    monkeypatch.setattr(gmail_service, "_connection_with_token", lambda _id: (dict(PENDING_HISTORY), "token"))
    monkeypatch.setattr(gmail_service, "owner_account_context", lambda *_a: owner)
    monkeypatch.setattr(owner_mail_automation, "window_since", lambda _connection, chosen: max(chosen, OCT_1))
    history, queries = [], []
    monkeypatch.setattr(gmail_service, "_list_message_page", lambda _s, query, **_k: history.append(query) or ([], None))
    monkeypatch.setattr(gmail_service, "_list_message_refs", lambda _s, query, _limit: queries.append(query) or [])
    updates = _Db()
    monkeypatch.setattr(gmail_service, "get_connection", lambda: updates)
    result = gmail_service._sync_connection(12, service=object())
    return result, history, queries, updates


def test_an_owner_gmail_sync_reads_the_current_month_and_never_the_history(monkeypatch):
    result, history, queries, updates = _gmail_sync(monkeypatch, owner=True)
    assert history == [], "no history page is read for the Owner"
    assert f"after:{gmail_service._cr_midnight_epoch(OCT_1)}" in queries[0] and "newer_than" not in queries[0]
    # The stored history cursor is left as it is (no page, no completion written).
    _query, params = updates.calls[-1]
    assert params[0] is False and params[1] is False and "page-4" not in params


def test_a_users_gmail_sync_keeps_its_history_scan(monkeypatch):
    _result, history, _queries, _updates = _gmail_sync(monkeypatch, owner=False)
    assert len(history) == 1 and f"after:{gmail_service._cr_midnight_epoch(date(2026, 1, 1))}" in history[0]


def test_an_owner_outlook_sync_reads_the_current_month_and_never_the_history(monkeypatch):
    connection = {"id": 7, "account_id": "account-o", "workspace_id": "workspace-o", "granted_scopes": ["Mail.Read"],
                  "refresh_token_secret_id": "secret", **{k: PENDING_HISTORY[k] for k in
                  ("import_scope", "import_since", "initial_scan_completed_at", "initial_scan_page_token")}}
    reads = iter([SimpleNamespace(fetchone=lambda: connection)])

    class Read(_Db):
        def execute(self, query, params=()):
            return next(reads)

    updates = _Db()
    connections = iter([Read(), updates])
    monkeypatch.setattr(ms, "get_connection", lambda: next(connections))
    monkeypatch.setattr(ms, "_has_active_vip_access", lambda *_a: True)
    monkeypatch.setattr(ms, "_vault_read", lambda *_a: "refresh")
    monkeypatch.setattr(ms, "_refresh", lambda *_a: "access")
    monkeypatch.setattr(ms, "owner_account_context", lambda *_a: True)
    monkeypatch.setattr(owner_mail_automation, "window_since", lambda _connection, chosen: max(chosen, OCT_1))
    calls = []
    monkeypatch.setattr(ms, "_graph_get", lambda _token, path, params=None: calls.append((path, params)) or {"value": []})
    result = ms.sync_connection(7)
    assert calls[0][0] == "/me/messages", "the stored history page link is never followed"
    _query, params = updates.calls[-1]
    assert params[1] == PENDING_HISTORY["initial_scan_page_token"] and params[2] is False, "the stored cursor is kept"
    assert calls[0][1]["$filter"] == "receivedDateTime ge 2026-10-01T00:00:00-06:00"
    assert result["scan_scope"] == "recent"


@pytest.mark.parametrize(("owner", "expected"), [(True, "auto_saved"), (False, "pending")])
def test_only_an_owner_candidate_reaches_the_learned_rule_save(monkeypatch, owner, expected):
    db = _Db({"INSERT INTO finva_email_candidates": {"id": 55}})
    for name in ("discover_candidate_account", "link_received_payroll"):
        monkeypatch.setattr(gmail_service, name, lambda *_a, **_k: None)
    monkeypatch.setattr(gmail_service, "resolve_candidate", lambda _conn, _id: {"status": "pending"})
    monkeypatch.setattr(gmail_service, "legacy_transaction_for_message", lambda *_a, **_k: None)
    monkeypatch.setattr(gmail_service, "owner_account_context", lambda *_a: owner)
    saved = []
    monkeypatch.setattr(owner_mail_automation, "auto_save", lambda _conn, candidate_id: saved.append(candidate_id) or "auto_saved")
    candidate = {key: None for key in (
        "movement_index", "source_type", "source_provider", "source_record_key", "institution_country", "transaction_date",
        "transaction_time", "description", "amount", "currency", "original_amount", "original_currency", "transaction_type",
        "movement_direction", "movement_kind", "category", "bank", "source_account_label", "source_account_reference",
        "destination_account_reference", "counterparty", "external_reference", "parser_name", "parser_version",
        "extraction_method", "confidence", "uncertainty_reason", "dedupe_key", "is_internal_transfer", "raw_payload")}
    resolution = gmail_service._insert_finva_candidate(
        db, email_message_id=7, candidate=candidate, gmail_message_id="gmail-1",
        connection={"id": 3, "account_id": "account-o", "workspace_id": "workspace-o", "legacy_user_id": 91},
    )
    assert resolution["status"] == expected
    assert saved == ([55] if owner else []), "a DINCR User's movement is never saved without confirmation"


@pytest.mark.parametrize("resolved", ["duplicate", "internal_transfer"])
def test_a_duplicate_or_internal_transfer_never_reaches_the_save(monkeypatch, resolved):
    db = _Db({"INSERT INTO finva_email_candidates": {"id": 56}})
    for name in ("discover_candidate_account", "link_received_payroll"):
        monkeypatch.setattr(gmail_service, name, lambda *_a, **_k: None)
    monkeypatch.setattr(gmail_service, "resolve_candidate", lambda _conn, _id: {"status": resolved})
    monkeypatch.setattr(gmail_service, "legacy_transaction_for_message", lambda *_a, **_k: None)
    monkeypatch.setattr(gmail_service, "owner_account_context", lambda *_a: True)
    monkeypatch.setattr(owner_mail_automation, "auto_save", lambda *_a: pytest.fail("only a pending candidate is evaluated"))
    candidate = {key: None for key in (
        "movement_index", "source_type", "source_provider", "source_record_key", "institution_country", "transaction_date",
        "transaction_time", "description", "amount", "currency", "original_amount", "original_currency", "transaction_type",
        "movement_direction", "movement_kind", "category", "bank", "source_account_label", "source_account_reference",
        "destination_account_reference", "counterparty", "external_reference", "parser_name", "parser_version",
        "extraction_method", "confidence", "uncertainty_reason", "dedupe_key", "is_internal_transfer", "raw_payload")}
    resolution = gmail_service._insert_finva_candidate(
        db, email_message_id=8, candidate=candidate, gmail_message_id="gmail-2",
        connection={"id": 3, "account_id": "account-o", "workspace_id": "workspace-o", "legacy_user_id": 91},
    )
    assert resolution["status"] == resolved
