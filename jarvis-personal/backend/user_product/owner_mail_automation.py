"""Owner-only automation for the standard mailbox pipeline.

Until 2026-09-24 the Owner's mail was read by a separate reader (email_monitor) that saved a
movement on its own when the workspace's learned rules allowed it: a ``classify`` rule with
``allow_auto_commit`` and a confidence of at least ``AUTO_COMMIT_CONFIDENCE``, in colones. That
reader read only the current month. When the Owner moved to the standard per-mailbox flow,
both behaviours were lost: every Owner movement waited for review and the first syncs started
scanning the year's history, which the Owner's reconstructed ledger already covers.

This module restores both, for the Owner only. Every entry point is reached solely after
``owner_account_context`` (stored records, never a request field) said the connection's account
and workspace are the verified Owner's; DINCR Users never reach it and keep confirming every
movement in Por revisar.

- ``window_since``: the Owner reads mail from the first day of the current month (Costa Rica),
  never before the connection's chosen date, and runs no history scan. Earlier months stay as
  the Owner recorded or reconstructed them.
- ``auto_save``: a pending movement candidate is saved as a transaction, through the same
  transaction and event writers as a manual confirmation, when the learned rules allow it. It
  stays pending (for review) whenever anything is uncertain: no matching rule, low confidence,
  another currency, an internal transfer, a transfer whose rule does not name both accounts, a
  possible match from another source, a statement row, no Owner identity for the event, a transaction of the same amount
  within a day (possibly the same movement already recorded) or any error while saving. One
  save at a time per workspace, so two mailboxes with the same notice cannot both save it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from backend.user_product import mail_oauth

logger = logging.getLogger(__name__)

AUTO_SAVED_NOTE = "Guardado automáticamente desde un correo bancario por una de tus reglas aprendidas."
NEAR_DUPLICATE_DAYS = 1


def window_since(connection: dict[str, Any], chosen: date, today: date | None = None) -> date:
    """First day of mail the Owner's syncs read: the current month, never before the chosen date."""
    current = today or datetime.now(mail_oauth.CR_TZ).date()
    return max(chosen, current.replace(day=1))


def _account_ownership(conn, workspace_id: str, reference: Any) -> str | None:
    """'own' / 'counterparty' for an account the Owner's private profile knows, by its last 4 digits."""
    digits = "".join(ch for ch in str(reference or "") if ch.isdigit())
    if len(digits) < 4:
        return None
    row = conn.execute(
        """SELECT ownership FROM email_financial_accounts
           WHERE workspace_id=%s AND account_last4=%s AND active=TRUE LIMIT 1""",
        (workspace_id, digits[-4:]),
    ).fetchone()
    return str(row["ownership"]) if row else None


def _owner_direction(conn, workspace_id: str, candidate: dict[str, Any]) -> str:
    """The movement's direction; when the notice does not say it, the Owner's known accounts do.

    The retired reader's parser gave a transfer from an own account to a third party the direction
    'out' (and the reverse 'in'); the standard pipeline leaves it 'unknown', which no learned rule
    with a direction can match. Two own accounts (an internal transfer) keep 'unknown'.
    """
    direction = str(candidate.get("movement_direction") or "unknown")
    if direction != "unknown":
        return direction
    origin = _account_ownership(conn, workspace_id, candidate.get("source_account_reference"))
    destination = _account_ownership(conn, workspace_id, candidate.get("destination_account_reference"))
    if origin == "own" and destination == "counterparty":
        return "out"
    if origin == "counterparty" and destination == "own":
        return "in"
    return direction


def _rule_pins_both_accounts(conn, workspace_id: str, ruled: dict[str, Any]) -> bool:
    if not ruled.get("personal_rule_id"):
        return False
    row = conn.execute(
        """SELECT origin_account_key,destination_account_key FROM email_classification_rules
           WHERE id=%s AND workspace_id=%s""",
        (int(ruled["personal_rule_id"]), workspace_id),
    ).fetchone()
    return bool(row and row["origin_account_key"] and row["destination_account_key"])


def _near_duplicate(conn, workspace_id: str, transaction_date: Any, amount: Any) -> bool:
    """A transaction of the same amount within a day may be this movement already recorded."""
    return bool(conn.execute(
        """SELECT 1 FROM transactions
           WHERE workspace_id=%s AND transaction_date BETWEEN %s::date - %s AND %s::date + %s
             AND ABS(amount - %s) < 0.01
           LIMIT 1""",
        (workspace_id, transaction_date, NEAR_DUPLICATE_DAYS, transaction_date, NEAR_DUPLICATE_DAYS, amount),
    ).fetchone())


def auto_save(conn, candidate_id: int) -> str | None:
    """Save an Owner candidate its learned rules allow; None leaves it pending. Caller commits."""
    from backend.email_monitor.personal_rules import apply_workspace_email_rules
    from backend.finance.category_catalog import normalize_category, owner_account_context
    from backend.user_product.candidate_resolution import _transfer_like
    from backend.email_monitor.service import AUTO_COMMIT_CONFIDENCE
    from backend.user_product.candidate_currency import native_money, transaction_amounts
    from backend.user_product.gmail_service import _create_candidate_transaction, _publish_confirmed_financial_input

    row = conn.execute(
        """SELECT c.*,g.legacy_user_id,a.base_currency AS account_base_currency,a.legacy_allowed_user_id
           FROM finva_email_candidates c
           JOIN finva_email_messages m ON m.id=c.email_message_id
           JOIN finva_gmail_connections g ON g.id=m.connection_id
           JOIN accounts a ON a.id=c.account_id
           WHERE c.id=%s FOR UPDATE OF c""",
        (candidate_id,),
    ).fetchone()
    if not row:
        return None
    candidate = dict(row)
    # A second barrier: whatever the caller decided, only the verified Owner's stored account
    # and workspace may be saved without a confirmation.
    owner = owner_account_context(conn, candidate["account_id"], candidate["workspace_id"])
    if not owner:
        return None
    if (candidate["status"] != "pending" or candidate.get("is_internal_transfer")
            or candidate.get("source_type") == "statement" or not candidate.get("legacy_allowed_user_id")):
        return None
    # Uncertain for the resolver: a possible match from another source (its statement copy, the
    # other mailbox). A human decides.
    if candidate.get("resolution_reason") or candidate.get("related_candidate_id"):
        return None
    native_currency, native_amount = native_money(candidate)
    if native_currency != "CRC":
        return None  # a converted amount is never saved unreviewed
    ruled = apply_workspace_email_rules(conn, str(candidate["workspace_id"]), {
        "email_kind": "movement",
        "description": candidate["description"],
        "raw_description": candidate["description"],
        "movement_direction": _owner_direction(conn, str(candidate["workspace_id"]), candidate),
        "origin_account": candidate.get("source_account_reference"),
        "destination_account": candidate.get("destination_account_reference"),
        "transaction_type": candidate["transaction_type"],
        "category": candidate["category"],
        "confidence": candidate.get("confidence"),
    })
    if (ruled.get("email_kind") != "movement" or not ruled.get("auto_commit_allowed")
            or float(ruled.get("confidence") or 0) < AUTO_COMMIT_CONFIDENCE):
        return None
    # A transfer is saved only when the learned rule names both of its accounts (as the retired
    # reader's rules did): one side of an unknown transfer whose pair may still arrive waits.
    if _transfer_like(candidate) and not _rule_pins_both_accounts(conn, str(candidate["workspace_id"]), ruled):
        return None
    # One automatic save at a time per workspace: two mailboxes syncing the same bank notice in
    # parallel must see each other's transaction (the lock ends with the caller's transaction).
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"owner_mail_auto_save:{candidate['workspace_id']}",))
    if _near_duplicate(conn, str(candidate["workspace_id"]), candidate["transaction_date"], native_amount):
        return None
    values = {
        "transaction_date": candidate["transaction_date"],
        "description": str(ruled.get("description") or candidate["description"]),
        "amount": native_amount,
        "transaction_type": str(ruled.get("transaction_type") or candidate["transaction_type"]),
        "category": str(ruled.get("category") or candidate["category"]),
    }
    # A failure here (an amount the writers refuse, a constraint) must not lose the candidate:
    # it rolls back to this point and the movement waits for review like any other.
    conn.execute("SAVEPOINT owner_mail_auto_save")
    try:
        money = transaction_amounts(native_currency, values["amount"], candidate.get("account_base_currency"), None)
        transaction_id = _create_candidate_transaction(conn, candidate, values, money, owner=owner, note=AUTO_SAVED_NOTE)
        _publish_confirmed_financial_input(
            conn, candidate, values, transaction_id, int(candidate["legacy_allowed_user_id"]), money, owner=owner,
        )
        conn.execute(
            """UPDATE finva_email_candidates
               SET transaction_id=%s,description=%s,transaction_type=%s,category=%s,
                   status='auto_saved',resolution_reason='owner_learned_rule',updated_at=NOW()
               WHERE id=%s""",
            (transaction_id, values["description"].strip(), values["transaction_type"],
             normalize_category(values["category"], values["transaction_type"], owner=owner), candidate_id),
        )
    except Exception as exc:
        conn.execute("ROLLBACK TO SAVEPOINT owner_mail_auto_save")
        logger.warning("Owner learned-rule save skipped error=%s", type(exc).__name__)
        return None
    conn.execute("RELEASE SAVEPOINT owner_mail_auto_save")
    return "auto_saved"

