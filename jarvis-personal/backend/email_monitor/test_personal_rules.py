from backend.email_monitor.personal_rules import apply_workspace_email_rules


ACCOUNTS = [
    {"account_key": "multimoney_6126", "account_last4": "6126", "ownership": "own", "display_name": "MultiMoney"},
    {"account_key": "bac_2572", "account_last4": "2572", "ownership": "own", "display_name": "BAC"},
    {"account_key": "sidey_7679", "account_last4": "7679", "ownership": "counterparty", "display_name": "Sidey"},
]

RULES = [
    {
        "id": 1,
        "name": "lavanderia_sidey",
        "priority": 200,
        "concept_pattern": "ropa",
        "match_mode": "exact",
        "direction": "out",
        "origin_account_key": "multimoney_6126",
        "destination_account_key": "sidey_7679",
        "action": "classify",
        "output_description": "Lavado y doblado de ropa",
        "transaction_type": "expense",
        "category": "Servicios",
        "allow_auto_commit": True,
        "review_reason": "Pago recurrente de lavandería reconocido.",
        "metadata": {},
    }
]


class _Conn:
    def execute(self, sql, _params=()):
        if "to_regclass" in sql:
            return _Result([{"accounts_ready": True, "rules_ready": True}])
        if "FROM email_financial_accounts" in sql:
            return _Result(ACCOUNTS)
        if "FROM email_classification_rules" in sql:
            return _Result(RULES)
        raise AssertionError(sql)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def test_own_account_transfer_is_ignored():
    parsed = {
        "email_kind": "movement",
        "description": "INVERSIÓN VISTA SMART COL",
        "movement_direction": "out",
        "origin_account": "CRC CR42****2572",
        "destination_account": "CRC CR74****6126",
    }
    result = apply_workspace_email_rules(_Conn(), "workspace", parsed)
    assert result["email_kind"] == "ignored"
    assert result["transaction_type"] == "internal_transfer"
    assert result["auto_commit_allowed"] is False


def test_exact_counterparty_rule_can_enable_auto_commit():
    parsed = {
        "email_kind": "movement",
        "description": "Ropa",
        "movement_direction": "out",
        "origin_account": "KENNETH / CRC CR74****6126",
        "destination_account": "SIDEY / CRC CR44****7679",
        "confidence": 0.97,
    }
    result = apply_workspace_email_rules(_Conn(), "workspace", parsed)
    assert result["description"] == "Lavado y doblado de ropa"
    assert result["transaction_type"] == "expense"
    assert result["category"] == "Servicios"
    assert result["auto_commit_allowed"] is True


def test_unknown_movement_never_auto_commits():
    parsed = {
        "email_kind": "movement",
        "description": "Concepto nuevo",
        "movement_direction": "out",
        "confidence": 0.99,
    }
    result = apply_workspace_email_rules(_Conn(), "workspace", parsed)
    assert result["auto_commit_allowed"] is False
