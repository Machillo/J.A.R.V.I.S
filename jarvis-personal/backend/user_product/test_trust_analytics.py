from backend.user_product import trust_analytics


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _Result(self.rows)


def test_summary_measures_observed_decisions_and_rates():
    result = trust_analytics.summarize_trust_rows([
        {
            "institution_country": "CR", "bank": "bac", "source_type": "email",
            "source_provider": "gmail", "parser_name": "bac_card", "parser_version": "3",
            "reviewed": 10, "accepted_unchanged": 7, "corrected": 2, "rejected": 1, "pending": 4,
        },
        {
            "institution_country": "CR", "bank": "popular", "source_type": "statement",
            "source_provider": "pdf", "parser_name": "popular_statement", "parser_version": "1",
            "reviewed": 5, "accepted_unchanged": 3, "corrected": 1, "rejected": 1, "pending": 2,
        },
    ])

    assert result["totals"] == {
        "reviewed": 15, "accepted_unchanged": 10, "corrected": 3, "rejected": 2,
        "pending": 6, "acceptance_rate": 66.67, "correction_rate": 20.0, "rejection_rate": 13.33,
    }
    assert result["segments"][0]["acceptance_rate"] == 70.0


def test_query_is_scoped_and_segmented(monkeypatch):
    connection = _Connection([])
    monkeypatch.setattr(trust_analytics, "get_current_account_id", lambda: "account-a")
    monkeypatch.setattr(trust_analytics, "get_current_workspace_id", lambda: "workspace-a")
    monkeypatch.setattr(trust_analytics, "get_connection", lambda: connection)

    result = trust_analytics.get_gmail_trust_analytics()

    query, params = connection.calls[0]
    assert "account_id=%s AND workspace_id=%s" in query
    assert "cardinality(corrected_fields)>0" in query
    assert "GROUP BY institution_country,bank,source_type,source_provider,parser_name,parser_version" in query
    assert params == ("account-a", "workspace-a")
    assert result["totals"]["acceptance_rate"] == 0.0
