"""The mailbox identity backfill writes nothing when its result is ambiguous."""
import pytest

from backend.scripts.backfill_mailbox_identity import Ambiguous, plan

ROWS = [{"id": 1}, {"id": 2}, {"id": 3}]


def test_resolved_rows_get_the_provider_identity_and_unresolved_keep_the_address():
    keys = {1: "google:1", 2: None, 3: "email:x@example.com"}
    updates, counts = plan(ROWS, set(), lambda row: keys[row["id"]])
    assert updates == {1: "google:1"} and counts == {"resolved": 1, "unresolved": 2}


def test_two_connections_resolving_to_one_identity_abort():
    with pytest.raises(Ambiguous):
        plan(ROWS[:2], set(), lambda row: "google:same")


def test_an_identity_already_live_elsewhere_aborts():
    with pytest.raises(Ambiguous):
        plan(ROWS[:1], {"google:1"}, lambda row: "google:1")
