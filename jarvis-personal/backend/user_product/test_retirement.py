"""RT-1 — Retiro: what is stored and refused. Unknown stays unknown; reading never writes."""
import pytest
from fastapi import HTTPException

from backend.user_product import retirement


@pytest.fixture
def store(monkeypatch):
    state = {}
    writes = []
    monkeypatch.setattr(retirement, "get_preference", lambda key, default=None: state.get(key, default))

    def save(key, value):
        writes.append(key)
        state[key] = value
        return {"status": "OK"}
    monkeypatch.setattr(retirement, "set_preference", save)
    return state, writes


def test_nothing_declared_is_unknown_not_zero(store):
    _, writes = store
    assert retirement.get_retirement() == {"config": {"rop_balance": None, "voluntary_balance": None, "birth_year": None, "retire_age": 65}}
    assert writes == [], "reading never writes"


def test_a_save_keeps_what_was_not_sent_and_a_null_clears(store):
    state, _ = store
    retirement.update_retirement({"rop_balance": 2_500_000, "birth_year": 1995})
    retirement.update_retirement({"voluntary_balance": 300_000})
    assert retirement.get_retirement()["config"] == {"rop_balance": 2_500_000.0, "voluntary_balance": 300_000.0, "birth_year": 1995, "retire_age": 65}
    retirement.update_retirement({"voluntary_balance": None, "retire_age": 60})
    assert state["retirement"]["voluntary_balance"] is None and state["retirement"]["retire_age"] == 60


@pytest.mark.parametrize("payload", [{"rop_balance": -1}, {"birth_year": 1800}, {"birth_year": "1990"}, {"retire_age": 30}])
def test_invalid_values_are_refused(store, payload):
    with pytest.raises(HTTPException) as refused:
        retirement.update_retirement(payload)
    assert refused.value.status_code == 422
