from datetime import date

from backend.user_product.candidate_resolution import _paired_owned_transfer, resolve_candidate, semantic_fingerprint


class _Result:
    def __init__(self, one=None, rows=None):
        self.one = one
        self.rows = rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return next(self.results)


def _candidate(**changes):
    candidate = {
        "id": 9, "account_id": "account-a", "workspace_id": "workspace-a",
        "transaction_date": date(2026, 9, 21), "transaction_time": "10:15:00",
        "description": "SINPE a ahorro", "amount": 25000, "currency": "CRC",
        "bank": "bac", "external_reference": "ABC-123",
        "source_account_reference": "CR00****1111",
        "destination_account_reference": "CR00****2222",
        "raw_payload": {"transaction_type": "transfer", "movement_direction": "out", "category": "Transferencia"},
    }
    candidate.update(changes)
    return candidate


def test_semantic_fingerprint_is_source_independent():
    email = _candidate(source_type="email", source_provider="gmail")
    statement = _candidate(source_type="statement", source_provider="pdf")
    assert semantic_fingerprint(email) == semantic_fingerprint(statement)


def test_fingerprint_without_reference_requires_time_account_and_description():
    assert semantic_fingerprint(_candidate(external_reference=None, transaction_time=None)) is None


def test_marks_duplicate_and_links_original_candidate():
    connection = _Connection([
        _Result(one=_candidate()), _Result(one={"id": 4}),
        _Result(one={"id": 4, "status": "pending", "related_candidate_id": None}),  # root of the match
        _Result(),
    ])
    result = resolve_candidate(connection, 9)
    assert result == {"status": "duplicate", "related_candidate_id": 4}
    query, params = connection.calls[-1]
    assert "status='duplicate'" in query
    assert params[-2:] == (4, 9)


def test_marks_internal_only_when_two_distinct_confirmed_accounts_match():
    connection = _Connection([
        _Result(one=_candidate(external_reference=None)), _Result(one=None), _Result(rows=[]),
        _Result(one={"id": 11}), _Result(one={"id": 22}), _Result(),
    ])
    result = resolve_candidate(connection, 9)
    assert result == {"status": "internal_transfer"}
    query, params = connection.calls[-1]
    assert "transaction_type=CASE" in query
    assert params[1] is True
    assert params[-2:] == ("confirmed_owned_endpoints", 9)


def test_links_one_possible_cross_source_match_without_auto_rejecting():
    statement = _candidate(source_type="statement", external_reference=None)
    connection = _Connection([
        _Result(one=statement), _Result(one=None),
        _Result(rows=[{"id": 4, "description": "SINPE A AHORRO", "source_account_reference": "1111", "destination_account_reference": None,
                       "transaction_date": date(2026, 9, 21), "transaction_type": "transfer", "status": "pending", "transaction_id": None,
                       "amount": 25000, "currency": "CRC", "original_amount": None, "original_currency": None}]),
        _Result(one=None), _Result(one=None), _Result(),
    ])
    result = resolve_candidate(connection, 9)
    assert result == {"status": "pending"}
    query, params = connection.calls[-1]
    assert "related_candidate_id=%s" in query
    assert params[-3:] == (4, "possible_cross_source_match", 9)


def test_opposite_owned_notifications_pair_with_distinct_accounts_and_close_times():
    candidate = _candidate(
        movement_kind="transfer", movement_direction="out", external_reference=None,
        destination_account_reference=None,
    )
    connection = _Connection([_Result(rows=[{
        "id": 10, "transaction_date": date(2026, 9, 21),
        "transaction_time": "10:17:00", "account_last4": "2222",
        "source_account_reference": None, "destination_account_reference": "2222",
        "external_reference": None,
    }])])
    assert _paired_owned_transfer(connection, candidate, 11) == 10
    assert "a.ownership_status='own'" in connection.calls[0][0]
    assert "c.status='pending'" in connection.calls[0][0]


def test_same_amount_at_different_time_or_ambiguous_pairs_stay_pending():
    candidate = _candidate(movement_kind="transfer", movement_direction="out", external_reference=None,
                           destination_account_reference=None)
    def other(id, time):
        return {"id": id, "transaction_date": date(2026, 9, 21),
                "transaction_time": time, "account_last4": "2222",
                "source_account_reference": None, "destination_account_reference": "2222",
                "external_reference": None}
    late = _Connection([_Result(rows=[other(10, "12:30:00")])])
    assert _paired_owned_transfer(late, candidate, 11) is None
    ambiguous = _Connection([_Result(rows=[other(10, "10:17:00"), other(12, "10:20:00")])])
    assert _paired_owned_transfer(ambiguous, candidate, 11) is None


def test_resolving_second_bank_notice_links_both_without_financial_transaction():
    candidate = _candidate(
        movement_kind="transfer", movement_direction="out", external_reference=None,
        destination_account_reference=None,
    )
    other = {"id": 10, "transaction_date": date(2026, 9, 21),
             "transaction_time": "10:17:00", "account_last4": "2222",
             "source_account_reference": None, "destination_account_reference": "2222",
             "external_reference": None}
    connection = _Connection([
        _Result(one=candidate), _Result(one=None), _Result(rows=[]), _Result(one={"id": 11}),
        _Result(rows=[other]), _Result(), _Result(),
    ])
    assert resolve_candidate(connection, 9) == {"status": "internal_transfer"}
    query, params = connection.calls[-2]
    assert "is_internal_transfer=%s" in query
    assert params[-3:] == (10, "paired_owned_transfer", 9)
    query, params = connection.calls[-1]
    assert "related_candidate_id=%s" in query
    assert params == (9, 10, "account-a", "workspace-a")
