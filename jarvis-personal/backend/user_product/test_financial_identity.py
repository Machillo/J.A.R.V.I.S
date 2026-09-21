from backend.user_product.financial_identity import _account_signal, discover_candidate_account


class _Result:
    def __init__(self, one=None):
        self.one = one

    def fetchone(self):
        return self.one


class _Connection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return _Result({"id": 42})


def test_account_signal_uses_destination_for_incoming_transfer():
    signal = _account_signal({
        "bank": "bac",
        "institution_country": "CR",
        "movement_direction": "in",
        "movement_kind": "transfer",
        "source_account_reference": "CR00****1111",
        "destination_account_reference": "CR00****2222",
        "source_account_label": "BAC Cuenta",
        "currency": "CRC",
    })

    assert signal["account_last4"] == "2222"
    assert signal["institution_code"] == "bac"
    assert signal["account_type"] == "checking"


def test_discovery_creates_pending_identity_and_links_candidate():
    connection = _Connection()
    result = discover_candidate_account(
        connection,
        candidate_id=8,
        candidate={
            "bank": "bac",
            "institution_country": "CR",
            "movement_direction": "out",
            "movement_kind": "card_purchase",
            "source_account_reference": "1234",
            "source_account_label": "BAC ****1234",
            "currency": "CRC",
        },
        account_id="account-a",
        workspace_id="workspace-a",
        legacy_user_id=7,
    )

    assert result == 42
    insert_query, insert_params = connection.calls[0]
    assert "'pending'" in insert_query
    assert insert_params[1:3] == ("workspace-a", "account-a")
    assert insert_params[7:10] == ("credit_card", "1234", "CRC")
    link_query, link_params = connection.calls[1]
    assert "financial_account_id=%s" in link_query
    assert link_params == (42, 8, "account-a", "workspace-a")
