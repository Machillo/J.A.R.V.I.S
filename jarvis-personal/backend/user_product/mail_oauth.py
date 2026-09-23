"""Server-side OAuth flows for mailbox connections (Gmail and Outlook).

The provider redirects to DINCR's callback from the system browser, outside
the DINCR session, so the callback alone cannot prove who is connecting a
mailbox. Linking therefore takes two steps:

1. Callback: the provider's code is accepted only for a stored, single-use,
   provider-bound, unexpired flow. DINCR redeems it with PKCE and parks the
   refresh token in Vault as *pending*.
2. Completion: the authenticated DINCR app of the account/workspace that
   started the flow redeems a one-time completion code delivered by the deep
   link. Only then is the mailbox attached.

Someone who receives another person's authorization link can finish the
consent in their own browser, but the mailbox is never attached to the
initiator: the completion code goes to the device that completed consent and
must be redeemed by the initiating account. Only hashes of the state and the
completion code are stored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
from typing import Any, Callable

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection

logger = logging.getLogger(__name__)

PROVIDERS = frozenset({"gmail", "microsoft"})
FLOW_TTL_MINUTES = 10
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


def _delete_secret(conn, secret_id: Any) -> None:
    if secret_id:
        conn.execute("DELETE FROM vault.secrets WHERE id=%s::uuid", (str(secret_id),))


def discard_stale_flows(conn, account_id: str | None = None) -> None:
    """Drop expired or failed flows and any refresh token they still hold."""
    scope, params = ("AND account_id=%s", (account_id,)) if account_id else ("", ())
    stale = conn.execute(
        f"""SELECT id,pending_secret_id FROM mail_oauth_flows
            WHERE (expires_at<=NOW() OR status='failed') AND status<>'completed' {scope}""",
        params,
    ).fetchall()
    for row in stale:
        _delete_secret(conn, row.get("pending_secret_id"))
    if stale:
        conn.execute("DELETE FROM mail_oauth_flows WHERE id = ANY(%s::uuid[])", ([str(row["id"]) for row in stale],))


def start_flow(provider: str) -> tuple[str, str]:
    """Create a flow for the current session. Returns (state, PKCE code_challenge)."""
    if provider not in PROVIDERS:
        raise ValueError("Unknown mail provider")
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    with get_connection() as conn:
        discard_stale_flows(conn, account_id)
        conn.execute(
            """INSERT INTO mail_oauth_flows(state_hash,provider,account_id,workspace_id,code_verifier,expires_at)
               VALUES(%s,%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 minute'))""",
            (_digest(state), provider, account_id, workspace_id, verifier, FLOW_TTL_MINUTES),
        )
        conn.commit()
    return state, pkce_challenge(verifier)


def claim_callback(provider: str, state: str | None) -> dict[str, Any] | None:
    """Consume the flow for this provider's callback exactly once."""
    if provider not in PROVIDERS or not state or len(state) > 256:
        return None
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE mail_oauth_flows SET status='callback',updated_at=NOW()
               WHERE state_hash=%s AND provider=%s AND status='started' AND expires_at>NOW()
               RETURNING id,account_id,workspace_id,code_verifier""",
            (_digest(state), provider),
        ).fetchone()
        conn.commit()
    return dict(row) if row else None


def fail_flow(flow_id: Any) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE mail_oauth_flows SET status='failed',code_verifier=NULL,updated_at=NOW()
               WHERE id=%s::uuid AND status IN ('started','callback')""",
            (str(flow_id),),
        )
        conn.commit()


def authorize_flow(conn, flow_id: Any, *, secret_id: str, mailbox: str, scopes: list[str]) -> str:
    """Park the Vault secret on the flow (same transaction) and issue the completion code."""
    completion = secrets.token_urlsafe(32)
    row = conn.execute(
        """UPDATE mail_oauth_flows SET status='authorized',code_verifier=NULL,completion_hash=%s,
                  pending_secret_id=%s::uuid,mailbox_address=%s,granted_scopes=%s,
                  expires_at=NOW()+(%s*INTERVAL '1 minute'),updated_at=NOW()
           WHERE id=%s::uuid AND status='callback' RETURNING id""",
        (_digest(completion), secret_id, mailbox, scopes, FLOW_TTL_MINUTES, str(flow_id)),
    ).fetchone()
    if not row:
        raise RuntimeError("OAuth flow is no longer awaiting its callback")
    return completion


def complete_flow(
    flow_id: str,
    completion: str,
    attach: Callable[[Any, dict[str, Any]], int],
) -> dict[str, Any]:
    """Attach the pending mailbox for the session that started the flow.

    ``attach(conn, flow)`` persists the provider connection in the same
    transaction and returns its id. Any mismatch fails closed and discards the
    pending refresh token.
    """
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    if not _UUID.match(str(flow_id or "")) or not completion or len(completion) > 256:
        raise HTTPException(status_code=409, detail="La autorización del correo no es válida. Volvé a conectarlo.")
    with get_connection() as conn:
        flow = conn.execute(
            """SELECT id,provider,account_id,workspace_id,status,completion_hash,pending_secret_id,
                      mailbox_address,granted_scopes,expires_at>NOW() AS active
               FROM mail_oauth_flows WHERE id=%s::uuid FOR UPDATE""",
            (flow_id,),
        ).fetchone()
        if (not flow or flow["status"] != "authorized" or not flow["active"]
                or not hmac.compare_digest(str(flow["completion_hash"] or ""), _digest(completion))):
            raise HTTPException(status_code=409, detail="La autorización del correo venció o ya se usó. Volvé a conectarlo.")
        flow = dict(flow)
        if str(flow["account_id"]) != str(account_id) or str(flow["workspace_id"]) != str(workspace_id):
            _delete_secret(conn, flow["pending_secret_id"])
            conn.execute(
                """UPDATE mail_oauth_flows SET status='failed',pending_secret_id=NULL,completion_hash=NULL,
                          updated_at=NOW() WHERE id=%s::uuid""",
                (flow_id,),
            )
            conn.commit()
            logger.warning("Mail OAuth completion rejected: flow belongs to another account provider=%s", flow["provider"])
            raise HTTPException(status_code=403, detail="Esta autorización de correo no pertenece a tu cuenta DINCR.")
        connection_id = attach(conn, flow)
        conn.execute(
            """UPDATE mail_oauth_flows SET status='completed',pending_secret_id=NULL,completion_hash=NULL,
                      updated_at=NOW() WHERE id=%s::uuid""",
            (flow_id,),
        )
        conn.commit()
    return {"connection_id": connection_id, "provider": flow["provider"]}


def complete_mail_connection(flow_id: str, completion: str) -> dict[str, Any]:
    """Route handler: attach the mailbox, then run the provider's first sync."""
    from backend.user_product import gmail_service, microsoft_mail  # provider modules import this one

    with get_connection() as conn:
        row = conn.execute("SELECT provider,account_id FROM mail_oauth_flows WHERE id=%s::uuid", (flow_id,)).fetchone() \
            if _UUID.match(str(flow_id or "")) else None
    provider = (row or {}).get("provider")
    if provider not in PROVIDERS:
        raise HTTPException(status_code=409, detail="La autorización del correo no es válida. Volvé a conectarlo.")
    legacy_user_id = gmail_service._financial_user_id_for_account(str(get_current_account_id()))
    attachers = {
        "gmail": lambda conn, flow: gmail_service._attach_gmail_connection(conn, flow, legacy_user_id),
        "microsoft": lambda conn, flow: microsoft_mail._attach_microsoft_connection(conn, flow, legacy_user_id),
    }
    result = complete_flow(flow_id, completion, attachers[provider])
    try:
        if result["provider"] == "gmail":
            gmail_service._after_gmail_connected(result["connection_id"])
        else:
            microsoft_mail.sync_connection(result["connection_id"])
    except Exception as exc:
        # The mailbox is connected; the first sync can be retried with "Actualizar".
        logger.warning("First mail sync after connection failed provider=%s error=%s", result["provider"], type(exc).__name__)
    return {"status": "connected", "provider": result["provider"]}
