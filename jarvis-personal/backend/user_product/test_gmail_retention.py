from backend.user_product import gmail_retention


class _Result:
    def __init__(self, total): self.total = total
    def fetchone(self): return {"total": self.total}


class _Connection:
    def __init__(self): self.calls = []; self.committed = False
    def __enter__(self): return self
    def __exit__(self, *_args): return None
    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _Result(len(self.calls))
    def commit(self): self.committed = True


def test_retention_policy_defaults_and_clamps(monkeypatch):
    monkeypatch.delenv("DINCR_GMAIL_REVIEW_EVIDENCE_DAYS", raising=False)
    monkeypatch.delenv("DINCR_GMAIL_METADATA_DAYS", raising=False)
    assert gmail_retention.retention_policy() == {
        "review_evidence_days": 30,
        "email_metadata_days": 90,
        "canonical_history": "until_account_deletion",
    }
    monkeypatch.setenv("DINCR_GMAIL_REVIEW_EVIDENCE_DAYS", "0")
    monkeypatch.setenv("DINCR_GMAIL_METADATA_DAYS", "99999")
    assert gmail_retention.retention_policy()["review_evidence_days"] == 1
    assert gmail_retention.retention_policy()["email_metadata_days"] == 3650


def test_cleanup_redacts_only_non_pending_evidence(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(gmail_retention, "get_connection", lambda: connection)
    result = gmail_retention.apply_gmail_retention()
    queries = [query for query, _ in connection.calls]
    assert "reviewed_at IS NOT NULL" in queries[0]
    assert "c.status='pending'" in queries[1]
    assert "c.status='pending'" in queries[2]
    assert connection.calls[0][1] == (30,)
    assert connection.calls[1][1] == (90,)
    assert connection.committed is True
    assert result == {
        "candidate_evidence_cleared": 1,
        "email_metadata_redacted": 2,
        "attachment_names_redacted": 3,
    }
