"""Deterministic deduplication between bank notifications and statement rows.

The real resolve_candidate and review code runs against an in-memory candidates
table. Every scenario checks how many transactions end up saved. Synthetic data only.
"""
import copy
import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import candidate_resolution as resolution
from backend.user_product import gmail_service

ACCOUNT, WORKSPACE = "account-sintetica", "workspace-sintetico"
DAY = date(2026, 9, 10)


def _rows(rows):
    rows = [dict(row) for row in rows]
    return SimpleNamespace(fetchone=lambda: rows[0] if rows else None, fetchall=lambda: rows)


class Table:
    def __init__(self):
        self.state = {"candidates": {}, "transactions": []}
        self.before_lock = None  # hook: simulate another transaction before the counterpart lock

    def connect(self):
        return Conn(self)


class Conn:
    def __init__(self, table):
        self.table, self.work = table, copy.deepcopy(table.state)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.table.state = copy.deepcopy(self.work)

    def execute(self, query, params=()):
        q = " ".join(query.split())
        rows = self.work["candidates"]
        scoped = lambda account, workspace: [c for c in rows.values() if (c["account_id"], c["workspace_id"]) == (account, workspace)]
        if q.startswith("SAVEPOINT") or q.startswith("RELEASE") or q.startswith("ROLLBACK"):
            return _rows([])
        if q.startswith("SELECT * FROM finva_email_candidates WHERE id=%s FOR UPDATE"):
            return _rows([rows[params[0]]] if params[0] in rows else [])
        if q.startswith("SELECT id FROM finva_email_candidates WHERE account_id=%s AND workspace_id=%s AND source_record_key=%s"):
            account, workspace, key, own = params
            return _rows(sorted(({"id": c["id"]} for c in scoped(account, workspace) if c.get("source_record_key") == key and c["id"] < own), key=lambda r: r["id"])[:1])
        if q.startswith("SELECT id FROM finva_email_candidates WHERE account_id=%s AND workspace_id=%s AND semantic_fingerprint=%s"):
            account, workspace, fingerprint, own = params
            return _rows(sorted(({"id": c["id"]} for c in scoped(account, workspace) if c.get("semantic_fingerprint") == fingerprint and c["id"] < own and c["status"] != "rejected"), key=lambda r: r["id"])[:1])
        if q.startswith("SELECT id,status,related_candidate_id FROM finva_email_candidates WHERE id=%s AND account_id=%s AND workspace_id=%s"):
            c = rows.get(params[0])
            return _rows([c] if c and (c["account_id"], c["workspace_id"]) == params[1:] else [])
        if q.startswith("SELECT id,status,transaction_id FROM finva_email_candidates WHERE id=%s AND account_id=%s AND workspace_id=%s FOR UPDATE"):
            if self.table.before_lock:
                self.table.before_lock(self.work)
            c = rows.get(params[0])
            return _rows([c] if c and (c["account_id"], c["workspace_id"]) == params[1:] else [])
        if q.startswith("SELECT c.id,c.status,c.transaction_id,c.transaction_date"):
            account, workspace, own, amount, original_amount, currency, bank, first, second, claimer, *reasons = params
            assert "(c.amount=%s OR c.original_amount=%s)" in q
            days = int(re.search(r"::date-(\d+)", q).group(1))
            statement = "c.source_type<>'statement'" in q
            # One-to-one: honour the NOT EXISTS clause of the real query.
            claims = [c for c in rows.values() if c["id"] != claimer and c["status"] == "duplicate"] \
                if "claimed.related_candidate_id=c.id" in q else []
            semantic_claims = "claimed.resolution_reason='same_semantic_movement' AND claimed.source_type<>c.source_type" in q

            def claimed(row):
                return any(c.get("related_candidate_id") == row["id"] and (
                    c.get("resolution_reason") in reasons
                    or (semantic_claims and c.get("resolution_reason") == "same_semantic_movement" and c["source_type"] != row["source_type"])
                ) for c in claims)
            return _rows(sorted((c for c in scoped(account, workspace)
                                 if c["id"] != own and (c["source_type"] != "statement") == statement
                                 and (c["amount"] == amount or (original_amount is not None and c.get("original_amount") == original_amount))
                                 and c["currency"] == currency and c["bank"] == bank
                                 and first - timedelta(days=days) <= c["transaction_date"] <= second + timedelta(days=days)
                                 and c["status"] in ("pending", "confirmed", "auto_saved") and not claimed(c)),
                                key=lambda c: c["id"]))
        if "FROM account_balances" in q or "JOIN account_balances" in q:
            return _rows([])  # no confirmed own accounts in these scenarios
        if q.startswith("UPDATE finva_email_candidates SET semantic_fingerprint=%s,status='duplicate'"):
            if "resolution_reason=%s" in q:
                fingerprint, related, reason, candidate_id = params
            else:
                (fingerprint, related, candidate_id), reason = params, "same_semantic_movement"
            rows[candidate_id].update(semantic_fingerprint=fingerprint, status="duplicate", related_candidate_id=related, resolution_reason=reason)
            return _rows([])
        if q.startswith("UPDATE finva_email_candidates SET semantic_fingerprint=%s,is_internal_transfer=%s"):
            fingerprint, internal, _i, base_type, _i2, _direction, _i3, _category, related, reason, candidate_id = params
            rows[candidate_id].update(semantic_fingerprint=fingerprint, is_internal_transfer=internal,
                                      related_candidate_id=related, resolution_reason=reason)
            return _rows([])
        if q.startswith("SELECT id FROM finva_email_candidates WHERE account_id=%s AND workspace_id=%s AND related_candidate_id=%s"):
            assert "AND (resolution_reason IN (%s,%s,%s) OR (resolution_reason='same_semantic_movement' AND source_type<>(SELECT" in q
            account, workspace, related, *reasons, rejected_id = params
            rejected_source = rows[rejected_id]["source_type"]
            return _rows(sorted(({"id": c["id"]} for c in scoped(account, workspace) if c.get("related_candidate_id") == related
                                 and c["status"] == "duplicate" and (
                                     c.get("resolution_reason") in reasons
                                     or (c.get("resolution_reason") == "same_semantic_movement" and c["source_type"] != rejected_source))),
                                key=lambda r: r["id"]))
        if q.startswith("UPDATE finva_email_candidates SET status='pending',related_candidate_id=NULL"):
            rows[params[0]].update(status="pending", related_candidate_id=None, resolution_reason=None)
            return _rows([])
        # review flow
        if q.startswith("SELECT c.*,g.legacy_user_id"):
            candidate_id, account, workspace = params
            c = rows.get(candidate_id)
            return _rows([{**c, "legacy_user_id": 90}] if c and (c["account_id"], c["workspace_id"]) == (account, workspace) else [])
        if q.startswith("INSERT INTO transactions"):
            transaction_id = 7000 + len(self.work["transactions"])
            self.work["transactions"].append({"id": transaction_id, "amount": params[2], "workspace_id": params[9]})
            return _rows([{"id": transaction_id}])
        if q.startswith("INSERT INTO financial_input_events") or q.startswith("INSERT INTO notification_jobs") or q.startswith("UPDATE finva_email_messages"):
            return _rows([])
        if q.startswith("UPDATE finva_email_candidates SET status='rejected'"):
            rows[params[0]]["status"] = "rejected"
            return _rows([])
        if q.startswith("UPDATE finva_email_candidates SET transaction_id=%s"):
            rows[params[-1]].update(transaction_id=params[0], status="confirmed")
            return _rows([])
        raise AssertionError(f"Unexpected query: {q[:110]}")


@pytest.fixture
def db(monkeypatch):
    table = Table()
    monkeypatch.setattr(gmail_service, "get_connection", table.connect)
    token = set_current_user({"id": 41, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    yield table
    reset_current_user(token)


def add(db, *, source="email", provider="gmail", description="AUTOMERCADO ESCAZU", amount=12500, currency="CRC",
        day=DAY, time="14:02:00", card="1234", reference=None, kind="card_purchase", transaction_type="expense",
        record_key=None, workspace=WORKSPACE, original_amount=None, original_currency=None):
    """Store a candidate and resolve it, as the mail pipeline does."""
    candidate_id = len(db.state["candidates"]) + 1
    db.state["candidates"][candidate_id] = {
        "id": candidate_id, "email_message_id": 500 + candidate_id, "account_id": ACCOUNT, "workspace_id": workspace,
        "source_type": source, "source_provider": "pdf" if source == "statement" else provider,
        "source_record_key": record_key or f"{provider}:msg-{candidate_id}:0",
        "transaction_date": day, "transaction_time": None if source == "statement" else time,
        "description": description, "amount": amount, "currency": currency, "bank": "bac",
        "original_amount": original_amount, "original_currency": original_currency,
        "transaction_type": transaction_type, "movement_kind": kind,
        "movement_direction": "out", "category": "Compras", "external_reference": reference,
        "source_account_reference": card, "destination_account_reference": None,
        "status": "pending", "transaction_id": None, "is_internal_transfer": False,
        "related_candidate_id": None, "resolution_reason": None, "semantic_fingerprint": None,
        "financial_account_id": None,
        "raw_payload": {"transaction_type": transaction_type, "movement_direction": "out", "category": "Compras"},
    }
    with db.connect() as conn:
        result = resolution.resolve_candidate(conn, candidate_id)
        conn.commit()
    return candidate_id, result


def accept(candidate_id):
    return gmail_service.review_gmail_candidate(candidate_id, "accept")


def reject(candidate_id):
    return gmail_service.review_gmail_candidate(candidate_id, "reject")


def candidate(db, candidate_id):
    return db.state["candidates"][candidate_id]


def test_accepted_notification_and_the_same_statement_row_save_one_transaction(db):
    email, _ = add(db)
    assert accept(email)["status"] == "confirmed"
    statement, result = add(db, source="statement", description="Automercado Escazú S.A.", record_key="statement:doc-a:0")
    assert result == {"status": "duplicate", "related_candidate_id": email}
    assert candidate(db, statement)["resolution_reason"] == "reconciled_with_existing_transaction"
    assert accept(statement)["status"] == "duplicate"  # a duplicate can never become a second transaction
    assert len(db.state["transactions"]) == 1


def test_statement_row_matching_a_pending_notification_waits_for_that_review(db):
    email, _ = add(db)
    statement, result = add(db, source="statement", description="AUTOMERCADO ESCAZU", record_key="statement:doc-a:0")
    assert result["status"] == "duplicate" and candidate(db, statement)["resolution_reason"] == "same_movement_other_source"
    accept(email)
    assert len(db.state["transactions"]) == 1


def test_notification_arriving_after_its_statement_row_is_the_duplicate(db):
    statement, _ = add(db, source="statement", record_key="statement:doc-a:0")
    email, result = add(db)
    assert result == {"status": "duplicate", "related_candidate_id": statement}


def test_same_amount_same_day_different_merchants_are_two_transactions(db):
    email, _ = add(db, description="AUTOMERCADO ESCAZU")
    statement, result = add(db, source="statement", description="FARMACIA FISCHEL", record_key="statement:doc-a:0")
    assert result == {"status": "pending"} and candidate(db, statement)["resolution_reason"] is None
    accept(email), accept(statement)
    assert len(db.state["transactions"]) == 2


def test_same_movement_received_in_gmail_and_outlook_is_saved_once(db):
    gmail, _ = add(db, provider="gmail", reference="AUT-778899")
    outlook, result = add(db, provider="microsoft", reference="AUT-778899")
    assert result == {"status": "duplicate", "related_candidate_id": gmail}
    accept(gmail), accept(outlook)
    assert len(db.state["transactions"]) == 1


def test_a_resent_notification_is_not_saved_twice(db):
    first, _ = add(db)
    resent, result = add(db)  # new message id, same time, card and merchant
    assert result == {"status": "duplicate", "related_candidate_id": first}
    accept(first), accept(resent)
    assert len(db.state["transactions"]) == 1


def test_the_same_statement_processed_again_is_not_saved_twice(db):
    first, _ = add(db, source="statement", record_key="statement:doc-a:0")
    again, result = add(db, source="statement", record_key="statement:doc-a:0")  # forwarded/resent document
    assert result == {"status": "duplicate", "related_candidate_id": first}
    assert candidate(db, again)["resolution_reason"] == "same_statement_row"
    accept(first), accept(again)
    assert len(db.state["transactions"]) == 1


@pytest.mark.parametrize(("notification", "statement"), [
    ("AUTOMERCADO ESCAZU", "Automercado Escazú S.A."),
    ("UBER *TRIP", "UBER TRIP HELP.UBER.COM"),
    ("Compra en PRICESMART ZAPOTE", "PRICESMART ZAPOTE 1234"),
    ("NETFLIX", "NETFLIX.COM"),
])
def test_normalizable_descriptions_match_with_enough_evidence(db, notification, statement):
    email, _ = add(db, description=notification)
    _row, result = add(db, source="statement", description=statement, record_key="statement:doc-a:0")
    assert result == {"status": "duplicate", "related_candidate_id": email}


def test_crc_and_usd_are_never_matched(db):
    add(db, amount=25, currency="USD")
    statement, result = add(db, source="statement", amount=25, currency="CRC", record_key="statement:doc-a:0")
    assert result == {"status": "pending"} and candidate(db, statement)["related_candidate_id"] is None


def test_transfers_are_never_collapsed_automatically(db):
    email, _ = add(db, description="SINPE ahorro", kind="transfer", transaction_type="transfer")
    statement, result = add(db, source="statement", description="SINPE ahorro", kind="transfer",
                            transaction_type="transfer", record_key="statement:doc-a:0")
    assert result == {"status": "pending"}
    assert candidate(db, statement)["resolution_reason"] == "possible_cross_source_match"
    assert candidate(db, statement)["related_candidate_id"] == email  # linked for the user, not merged


def test_two_legitimate_equal_purchases_are_not_merged_without_evidence(db):
    first, _ = add(db, time="09:00:00")
    second, second_result = add(db, time="18:30:00")  # same merchant, card, amount and day
    assert second_result == {"status": "pending"}
    row, result = add(db, source="statement", record_key="statement:doc-a:0")
    assert result == {"status": "pending"}  # two possible counterparts: the user decides
    assert candidate(db, row)["resolution_reason"] == "possible_cross_source_match"
    assert candidate(db, row)["related_candidate_id"] is None
    accept(first), accept(second)
    assert len(db.state["transactions"]) == 2


def test_one_notification_covers_only_one_of_two_identical_statement_rows(db):
    email, _ = add(db)
    first_row, first = add(db, source="statement", record_key="statement:doc-a:0")
    second_row, second = add(db, source="statement", record_key="statement:doc-a:1")
    assert first == {"status": "duplicate", "related_candidate_id": email}
    assert second == {"status": "pending"}  # the second identical purchase stays reviewable
    accept(email), accept(second_row)
    assert len(db.state["transactions"]) == 2


def test_rejecting_the_notification_puts_its_statement_copy_back_in_review(db):
    email, _ = add(db)
    statement, _ = add(db, source="statement", record_key="statement:doc-a:0")
    assert candidate(db, statement)["status"] == "duplicate"
    reject(email)
    assert candidate(db, statement)["status"] == "pending"
    assert accept(statement)["status"] == "confirmed"
    assert len(db.state["transactions"]) == 1


def test_a_rejected_notification_is_not_used_as_a_counterpart(db):
    email, _ = add(db)
    reject(email)
    _row, result = add(db, source="statement", record_key="statement:doc-a:0")
    assert result == {"status": "pending"}


def test_statement_rows_posted_days_later_are_only_flagged_for_review(db):
    email, _ = add(db)
    statement, result = add(db, source="statement", day=DAY + timedelta(days=2), record_key="statement:doc-a:0")
    assert result == {"status": "pending"}
    assert candidate(db, statement)["related_candidate_id"] == email


def test_other_workspaces_are_never_counterparts(db):
    add(db, workspace="workspace-ajeno")
    _row, result = add(db, source="statement", record_key="statement:doc-a:0")
    assert result == {"status": "pending"}


def test_a_single_generic_word_is_only_a_review_hint(db):
    email, _ = add(db, description="UBER")
    row, result = add(db, source="statement", description="UBER EATS", record_key="statement:doc-a:0")
    assert result == {"status": "pending"}
    assert (candidate(db, row)["resolution_reason"], candidate(db, row)["related_candidate_id"]) == ("possible_cross_source_match", email)


@pytest.mark.parametrize(("notification", "statement"), [("AUTO MERCADO", "AUTOMERCADO"), ("PRICESMART ZAPOTE", "PRICESMART ZAPOT")])
def test_spacing_or_truncated_names_are_linked_for_review(db, notification, statement):
    email, _ = add(db, description=notification)
    row, result = add(db, source="statement", description=statement, day=DAY + timedelta(days=1), record_key="statement:doc-a:0")
    assert result == {"status": "pending"}
    assert candidate(db, row)["related_candidate_id"] == email


def test_usd_purchases_converted_at_different_rates_match_by_the_original_amount(db):
    email, _ = add(db, amount=10395, original_amount=21, original_currency="USD")  # notification rate
    row, result = add(db, source="statement", amount=10500, original_amount=21, original_currency="USD",
                      record_key="statement:doc-a:0")  # statement rate
    assert result == {"status": "duplicate", "related_candidate_id": email}


def test_a_usd_purchase_never_matches_a_colon_purchase_of_the_same_converted_amount(db):
    add(db, amount=10395, original_amount=21, original_currency="USD")
    _row, result = add(db, source="statement", amount=10395, record_key="statement:doc-a:0")
    assert result == {"status": "pending"}


def test_rejecting_a_notification_with_a_resent_statement_never_hides_the_movement(db):
    """Review H1, scenario 1: notification, statement row, same PDF resent, reject."""
    email, _ = add(db)
    first, _ = add(db, source="statement", record_key="statement:doc-a:0")
    again, _ = add(db, source="statement", record_key="statement:doc-a:0")
    assert candidate(db, again)["related_candidate_id"] == email  # points at the root
    reject(email)
    states = {i: (candidate(db, i)["status"], candidate(db, i)["related_candidate_id"]) for i in (first, again)}
    assert states == {first: ("pending", None), again: ("duplicate", first)}
    assert accept(first)["status"] == "confirmed" and accept(again)["status"] == "duplicate"
    assert len(db.state["transactions"]) == 1


def test_rejecting_a_statement_with_copies_in_two_mailboxes_never_hides_the_movement(db):
    """Review H1, scenario 2: statement row, Gmail copy, Outlook copy, reject the statement row."""
    row, _ = add(db, source="statement", record_key="statement:doc-a:0", reference="AUT-1")
    gmail, _ = add(db, provider="gmail", reference="AUT-1")
    outlook, _ = add(db, provider="microsoft", reference="AUT-1")
    reject(row)
    visible = [i for i in (gmail, outlook) if candidate(db, i)["status"] == "pending"]
    assert len(visible) == 1  # exactly one reviewable copy, no cycle
    hidden = ({gmail, outlook} - set(visible)).pop()
    assert candidate(db, hidden)["related_candidate_id"] == visible[0]
    accept(gmail), accept(outlook)
    assert len(db.state["transactions"]) == 1


def test_a_counterpart_rejected_concurrently_is_never_used(db):
    """Review H2: the notification is rejected by another transaction before the lock."""
    email, _ = add(db)
    db.before_lock = lambda work: work["candidates"][email].update(status="rejected")
    row, result = add(db, source="statement", record_key="statement:doc-a:0")
    assert result == {"status": "pending"} and candidate(db, row)["related_candidate_id"] is None


def test_a_notification_claimed_through_its_bank_reference_covers_only_one_statement_row(db):
    """Review M4: a same_semantic_movement claim across sources is one-to-one too."""
    email, _ = add(db, reference="AUT-9")
    first, result = add(db, source="statement", reference="AUT-9", record_key="statement:doc-a:0")
    assert result["status"] == "duplicate" and candidate(db, first)["resolution_reason"] == "same_semantic_movement"
    reject(email)
    assert candidate(db, first)["status"] == "pending"  # the statement row goes back to review
