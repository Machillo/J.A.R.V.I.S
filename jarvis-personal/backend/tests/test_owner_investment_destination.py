"""The Owner's investment share goes to the savings account he names (invented names and rates)."""
from backend.ai import owner_investment_destination as dest


def _found(monkeypatch, value):
    return dest.destination(lambda key, default=None: value if key == dest.PREFERENCE_KEY else default)


def test_without_a_destination_nothing_changes(monkeypatch):
    items = [{"key": "inversion", "amount": 1000}]
    priority = {"kind": "investment", "title": "Construir patrimonio"}
    assert dest.apply(items, priority, _found(monkeypatch, None)) == priority
    assert "target_name" not in items[0]


def test_the_share_and_the_priority_name_the_account(monkeypatch):
    found = _found(monkeypatch, {"name": "Cuenta X", "annual_rate": 4})
    items = [{"key": "ataque_de_deuda", "amount": 5}, {"key": "inversion", "amount": 12500}]
    priority = dest.apply(items, {"kind": "investment", "title": "Construir patrimonio"}, found)
    assert items[1]["target_name"].startswith("Cuenta X")
    assert "12.500" in priority["title"] and "Cuenta X" in priority["title"]


def test_another_priority_keeps_its_words(monkeypatch):
    found = _found(monkeypatch, {"name": "Cuenta X", "annual_rate": 4})
    priority = {"kind": "debt", "title": "Atacar deuda"}
    assert dest.apply([{"key": "inversion", "amount": 0}], priority, found) == priority


def test_an_invalid_rate_or_name_is_ignored(monkeypatch):
    assert _found(monkeypatch, {"name": "Cuenta X", "annual_rate": 0}) is None
    assert _found(monkeypatch, {"name": "", "annual_rate": 4}) is None
    assert _found(monkeypatch, {"name": "Cuenta X", "annual_rate": "abc"}) is None


def test_a_failed_read_is_no_destination():
    def broken(*_):
        raise RuntimeError("no database")
    assert dest.destination(broken) is None
