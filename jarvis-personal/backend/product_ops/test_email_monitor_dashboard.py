from backend.product_ops.email_monitor_dashboard import build_email_monitor_dashboard


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(self, results):
        self.results = list(results)
        self.queries = []

    def execute(self, query, _params=()):
        self.queries.append(query)
        return _Result(self.results.pop(0))


def test_owner_email_dashboard_summarizes_truth_without_sensitive_content():
    connection = _Connection([
        [{"status": "processed", "total": 12}],
        [{
            "bank": "bac", "source_type": "email",
            "parser_name": "bac_card", "parser_version": "3", "movement_kind": "card_purchase",
            "pending": 2, "reviewed": 10, "accepted": 7, "corrected": 2, "rejected": 1,
        }],
        [{"status": "active", "total": 1, "with_error": 0}],
        [{"bank": "popular", "status": "candidates_ready", "parser_name": "popular_statement", "parser_version": "1", "total": 2, "movements_found": 8}],
        [{"ownership_status": "own", "total": 2}],
    ])

    result = build_email_monitor_dashboard(connection)

    assert result["totals"] == {
        "pending": 2, "reviewed": 10, "accepted": 7, "corrected": 2, "rejected": 1,
        "acceptance_rate": 70.0, "correction_rate": 20.0, "rejection_rate": 10.0,
    }
    assert result["candidates"][0]["movement_kind"] == "card_purchase"
    assert "raw_payload" not in " ".join(connection.queries).lower()
    assert "description" not in " ".join(connection.queries).lower()
    assert len(connection.queries) == 5
    queries = " ".join(connection.queries).lower()
    # Limited Use: humans see Gmail-derived data only aggregated, never per person.
    for personal in ("primary_email", "email AS", "account_id", "join accounts", "display_name"):
        assert personal.lower() not in queries


def test_owner_email_dashboard_handles_empty_database():
    result = build_email_monitor_dashboard(_Connection([[], [], [], [], []]))
    assert result["totals"]["acceptance_rate"] == 0.0
    assert result["candidates"] == []
