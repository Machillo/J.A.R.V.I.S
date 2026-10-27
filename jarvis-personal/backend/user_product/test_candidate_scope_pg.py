"""SEC-06 (defense in depth): a mail candidate is resolved only inside its own account and workspace.

`resolve_candidate` used to load and rewrite a candidate by its id alone, trusting every caller to
pass an id of its own workspace. It now takes the caller's account and workspace and filters every
read and write with them, so a stored link that ever pointed across workspaces
(`related_candidate_id`, which has no constraint tying it to the same workspace) can't reach another
account's candidate. Real PostgreSQL (the review test's schema); synthetic accounts A and B.
"""
from __future__ import annotations

import pytest

from backend.user_product.candidate_resolution import resolve_candidate
from backend.user_product.legacy_owner_mail import mark_legacy_duplicate
from backend.user_product.test_gmail_review_pg import (  # noqa: F401  (admin_uri and db are fixtures)
    ACC_A,
    ACC_B,
    USER_A,
    WS_A,
    WS_B,
    _candidate,
    _review,
    _state,
    admin_uri,
    db,
)

psycopg2 = pytest.importorskip("psycopg2")


def _row(conn, candidate_id):
    with conn.cursor() as cur:
        cur.execute("SELECT status, related_candidate_id, resolution_reason, updated_at FROM finva_email_candidates WHERE id=%s",
                    (candidate_id,))
        return cur.fetchone()


def test_another_workspaces_candidate_is_not_resolved_with_this_scope(db):
    from backend.core import database

    other = _candidate(db, account=ACC_B, workspace=WS_B)
    before = _row(db, other)
    with database.get_connection() as conn:
        assert resolve_candidate(conn, other, account_id=ACC_A, workspace_id=WS_A) == {"status": "missing"}
        conn.commit()
    assert _row(db, other) == before, "nothing of account B was read for writing or changed"


def test_rejecting_a_candidate_never_resolves_a_linked_candidate_of_another_workspace(db):
    own = _candidate(db)
    foreign = _candidate(db, account=ACC_B, workspace=WS_B)
    # A stored link that points across workspaces (nothing in the schema forbids it).
    with db.cursor() as cur:
        cur.execute("UPDATE finva_email_candidates SET related_candidate_id=%s, resolution_reason='paired_owned_transfer' WHERE id=%s",
                    (foreign, own))
    before = _row(db, foreign)
    assert _review(USER_A, own, "reject")["status"] == "rejected"
    assert _state(db, own)["status"] == "rejected"
    assert _row(db, foreign) == before, "account B's candidate is untouched"


def test_a_legacy_duplicate_mark_only_reaches_its_own_workspace(db):
    from backend.core import database

    other = _candidate(db, account=ACC_B, workspace=WS_B)
    with database.get_connection() as conn:
        mark_legacy_duplicate(conn, candidate_id=other, resolution={"status": "pending"}, account_id=ACC_A, workspace_id=WS_A)
        conn.commit()
    assert _row(db, other)[0] == "pending", "a candidate of account B is never marked from account A"
