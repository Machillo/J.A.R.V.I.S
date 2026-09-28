"""Authentication skips the identity writes only when nothing about the binding would change."""
from datetime import datetime, timedelta, timezone

from backend.auth import service

TOKEN_ID = "11111111-1111-1111-1111-111111111111"
NOW = datetime.now(timezone.utc)


def _row(**changes):
    row = {"supabase_user_id": TOKEN_ID, "role": "user", "last_login_at": (NOW - timedelta(minutes=1)).isoformat()}
    row.update(changes)
    return row


def test_a_bound_recent_identity_needs_no_write():
    assert service._identity_fresh(_row(), [_row()], TOKEN_ID) is True


def test_the_role_plays_no_part_because_login_never_writes_it():
    # backend/auth/owner_role.py: the stored role decides and OWNER_EMAILS only gates it.
    assert service._identity_fresh(_row(role="owner"), [_row(role="user")], TOKEN_ID) is True


def test_any_change_or_first_login_still_writes():
    stale = (NOW - timedelta(minutes=10)).isoformat()
    cases = [
        (_row(supabase_user_id=None), [_row()]),          # first login: the binding is written
        (_row(), [_row(supabase_user_id=None)]),          # account not bound yet
        (_row(last_login_at=stale), [_row()]),            # last login refreshed every 5 minutes
        (_row(), [_row(last_login_at=None)]),
        (_row(), []),                                     # no account row: let the normal path decide
    ]
    for app_user, accounts in cases:
        assert service._identity_fresh(app_user, accounts, TOKEN_ID) is False
