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
from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import psycopg2
from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection

logger = logging.getLogger(__name__)

PROVIDERS = frozenset({"gmail", "microsoft"})
FLOW_TTL_MINUTES = 10
# History the user chooses to import before the provider consent. Clients that do
# not send a choice keep the scan window that existed before the choice.
IMPORT_SCOPES = ("current_month", "current_year")
DEFAULT_IMPORT_SCOPE = "current_year"
CR_TZ = ZoneInfo("America/Costa_Rica")
# One live connection per mailbox across every DINCR account and workspace. The
# message is the same whatever the reason, so it never tells the person who is
# connecting whether (or where) the mailbox is already used.
MAILBOX_UNAVAILABLE = "No pudimos conectar este correo a tu cuenta. Si ya está conectado en otra cuenta DINCR, desconectalo ahí primero."
# Shown to the previous account after a verified takeover; its imported data stays.
MAILBOX_TAKEN_OVER = "Este correo se volvió a autorizar en otra cuenta DINCR y se desconectó de esta. Lo que ya importaste se conserva."
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


def canonical_mailbox(address: str | None) -> str:
    """The address DINCR compares mailboxes by; the stored google_email stays for display.

    Gmail ignores dots and "+tag" in gmail.com addresses, and googlemail.com is the
    same mailbox. Other providers are compared case-insensitively only. The SQL
    backfill in 20260926110000_mailbox_single_owner.sql computes the same value.
    """
    value = str(address or "").strip().lower()
    local, at, domain = value.rpartition("@")
    if not at:
        return value
    if domain in ("gmail.com", "googlemail.com"):
        return f"{local.split('+', 1)[0].replace('.', '')}@gmail.com"
    return value


def mailbox_key(provider: str, address: str | None, subject: str | None = None, tenant: str | None = None) -> str:
    """Stable mailbox identity: the provider's account id when known, else the canonical address.

    Google: the account's ``sub``. Microsoft: the Graph user ``id`` within its tenant.
    """
    if provider == "gmail" and subject:
        return f"google:{subject}"
    if provider == "microsoft" and subject and tenant:
        return f"microsoft:{tenant}:{subject}"
    return f"email:{canonical_mailbox(address)}"


def claim_mailbox(conn, *, provider: str, account_id: str, workspace_id: str, key: str, email: str,
                  is_entitled: Callable[[Any, str], bool]) -> None:
    """Make a mailbox this account/workspace just proved control of available to it, or refuse.

    One live connection per mailbox across every DINCR account and workspace. A
    live connection elsewhere is refused with a message that reveals nothing about
    it, unless it is stale: its provider access was lost ('reauthorization_required')
    or its account no longer has the plan that includes mail. A stale connection is
    taken over in this transaction:
    - it is disconnected and its token deleted (never reused, never revoked: with
      the same OAuth client, revoking it would revoke the new grant too);
    - its account keeps every message and transaction it imported (nothing moves);
    - the takeover is audited in mail_connection_takeovers (account ids only).
    Rows are locked, and the unique live-mailbox indexes close races between
    concurrent completions. The caller then attaches the mailbox.
    """
    rows = conn.execute(
        """SELECT id,account_id,status,refresh_token_secret_id FROM finva_gmail_connections
           WHERE status<>'disabled' AND NOT (account_id=%s AND workspace_id=%s)
             AND (mailbox_key=%s OR mailbox_email=%s
                  OR (mailbox_email IS NULL AND lower(btrim(google_email))=%s))
           ORDER BY id FOR UPDATE""",
        (account_id, workspace_id, key, email, email),
    ).fetchall()
    reasons = []
    for row in rows:
        if row["status"] == "reauthorization_required":
            reasons.append("access_lost")
        elif not is_entitled(conn, str(row["account_id"])):
            reasons.append("plan_inactive")
        else:
            raise HTTPException(status_code=409, detail=MAILBOX_UNAVAILABLE)
    for row, reason in zip(rows, reasons):
        conn.execute(
            """UPDATE finva_gmail_connections
               SET status='disabled',history_id=NULL,watch_expiration=NULL,initial_scan_page_token=NULL,
                   last_error=%s,updated_at=NOW()
               WHERE id=%s""",
            (MAILBOX_TAKEN_OVER, int(row["id"])),
        )
        _delete_secret(conn, row["refresh_token_secret_id"])
        conn.execute(
            """INSERT INTO mail_connection_takeovers(provider,previous_connection_id,previous_account_id,new_account_id,reason)
               VALUES(%s,%s,%s,%s,%s)""",
            (provider, int(row["id"]), str(row["account_id"]), account_id, reason),
        )
        logger.info("Mail connection taken over provider=%s reason=%s", provider, reason)


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


def normalized_import_scope(value: str | None) -> str:
    if value is None:
        return DEFAULT_IMPORT_SCOPE
    if value not in IMPORT_SCOPES:
        raise HTTPException(status_code=422, detail="Elegí desde este mes o desde este año.")
    return value


def import_since(scope: str | None, today: date | None = None) -> date:
    """First day to import: the 1st of the current month or January 1st (Costa Rica time)."""
    today = today or datetime.now(CR_TZ).date()
    return today.replace(day=1) if scope == "current_month" else date(today.year, 1, 1)


def start_flow(provider: str, import_scope: str | None = None) -> tuple[str, str]:
    """Create a flow for the current session. Returns (state, PKCE code_challenge)."""
    if provider not in PROVIDERS:
        raise ValueError("Unknown mail provider")
    scope = normalized_import_scope(import_scope)
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    with get_connection() as conn:
        discard_stale_flows(conn, account_id)
        conn.execute(
            """INSERT INTO mail_oauth_flows(state_hash,provider,account_id,workspace_id,code_verifier,import_scope,expires_at)
               VALUES(%s,%s,%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 minute'))""",
            (_digest(state), provider, account_id, workspace_id, verifier, scope, FLOW_TTL_MINUTES),
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


def rejected_callback_status(provider: str, state: str | None) -> str:
    """Status for a callback whose state could not be claimed.

    Browsers can deliver the provider redirect twice (a retried GET, a reloaded
    or restored tab). The replay is still rejected -- no token exchange and no
    completion code -- but it is reported as ``already_processed`` so the app
    does not present it as an expired authorization while the first delivery
    connects the mailbox. Unknown, expired, failed or cross-provider states
    stay ``invalid_state``.
    """
    if provider not in PROVIDERS or not state or len(state) > 256:
        return "invalid_state"
    with get_connection() as conn:
        row = conn.execute(
            "SELECT provider,status FROM mail_oauth_flows WHERE state_hash=%s",
            (_digest(state),),
        ).fetchone()
    if row and row["provider"] == provider and row["status"] in ("callback", "authorized", "completed"):
        return "already_processed"
    return "invalid_state"


def fail_flow(flow_id: Any) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE mail_oauth_flows SET status='failed',code_verifier=NULL,updated_at=NOW()
               WHERE id=%s::uuid AND status IN ('started','callback')""",
            (str(flow_id),),
        )
        conn.commit()


def authorize_flow(conn, flow_id: Any, *, secret_id: str, mailbox: str, scopes: list[str],
                   subject: str | None = None, tenant: str | None = None) -> str:
    """Park the Vault secret and the provider's mailbox identity on the flow; issue the completion code.

    ``mailbox``, ``subject`` and ``tenant`` come from the provider's own API with the
    new token, never from anything the user typed.
    """
    completion = secrets.token_urlsafe(32)
    row = conn.execute(
        """UPDATE mail_oauth_flows SET status='authorized',code_verifier=NULL,completion_hash=%s,
                  pending_secret_id=%s::uuid,mailbox_address=%s,granted_scopes=%s,
                  provider_subject=%s,provider_tenant=%s,
                  expires_at=NOW()+(%s*INTERVAL '1 minute'),updated_at=NOW()
           WHERE id=%s::uuid AND status='callback' RETURNING id""",
        (_digest(completion), secret_id, mailbox, scopes, subject, tenant, FLOW_TTL_MINUTES, str(flow_id)),
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

    Redeeming the same completion code again from the same account and
    workspace, before the flow expires, reports the existing result without
    attaching anything (the app may retry after losing the first response).
    Any other reuse is rejected.
    """
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    if not _UUID.match(str(flow_id or "")) or not completion or len(completion) > 256:
        raise HTTPException(status_code=409, detail="La autorización del correo no es válida. Volvé a conectarlo.")
    with get_connection() as conn:
        flow = conn.execute(
            """SELECT id,provider,account_id,workspace_id,status,completion_hash,pending_secret_id,
                      mailbox_address,granted_scopes,import_scope,provider_subject,provider_tenant,
                      expires_at>NOW() AS active
               FROM mail_oauth_flows WHERE id=%s::uuid FOR UPDATE""",
            (flow_id,),
        ).fetchone()
        if (not flow or flow["status"] not in ("authorized", "completed") or not flow["active"]
                or not hmac.compare_digest(str(flow["completion_hash"] or ""), _digest(completion))):
            raise HTTPException(status_code=409, detail="La autorización del correo venció o ya se usó. Volvé a conectarlo.")
        flow = dict(flow)
        if str(flow["account_id"]) != str(account_id) or str(flow["workspace_id"]) != str(workspace_id):
            if flow["status"] == "completed":
                logger.warning("Mail OAuth completion replay rejected: flow belongs to another account provider=%s", flow["provider"])
                raise HTTPException(status_code=403, detail="Esta autorización de correo no pertenece a tu cuenta DINCR.")
            _delete_secret(conn, flow["pending_secret_id"])
            conn.execute(
                """UPDATE mail_oauth_flows SET status='failed',pending_secret_id=NULL,completion_hash=NULL,
                          updated_at=NOW() WHERE id=%s::uuid""",
                (flow_id,),
            )
            conn.commit()
            logger.warning("Mail OAuth completion rejected: flow belongs to another account provider=%s", flow["provider"])
            raise HTTPException(status_code=403, detail="Esta autorización de correo no pertenece a tu cuenta DINCR.")
        if flow["status"] == "completed":
            return {"connection_id": None, "provider": flow["provider"], "already_completed": True}
        try:
            connection_id = attach(conn, flow)
        except (HTTPException, psycopg2.errors.UniqueViolation) as refused:
            # A refused mailbox is never left behind: the flow fails and its
            # pending refresh token is deleted now, not at some later cleanup.
            # The rollback released the flow's lock, so re-lock it and act only
            # if nobody completed it meanwhile with that same token.
            conn.rollback()
            still = conn.execute(
                "SELECT status,pending_secret_id FROM mail_oauth_flows WHERE id=%s::uuid FOR UPDATE",
                (flow_id,),
            ).fetchone()
            if still and still["status"] == "authorized" and str(still["pending_secret_id"]) == str(flow["pending_secret_id"]):
                _delete_secret(conn, flow["pending_secret_id"])
                conn.execute(
                    """UPDATE mail_oauth_flows SET status='failed',pending_secret_id=NULL,completion_hash=NULL,
                              updated_at=NOW() WHERE id=%s::uuid AND status='authorized'""",
                    (flow_id,),
                )
            conn.commit()
            if isinstance(refused, HTTPException):
                raise
            logger.warning("Mail OAuth completion lost a race for the same mailbox provider=%s", flow["provider"])
            raise HTTPException(status_code=409, detail=MAILBOX_UNAVAILABLE) from None
        # completion_hash is kept (a hash of a spent code) so the initiating
        # session can confirm the result idempotently until the flow expires.
        conn.execute(
            """UPDATE mail_oauth_flows SET status='completed',pending_secret_id=NULL,
                      updated_at=NOW() WHERE id=%s::uuid""",
            (flow_id,),
        )
        conn.commit()
    return {"connection_id": connection_id, "provider": flow["provider"], "already_completed": False}


def connection_import_window(existing: dict[str, Any] | None, flow: dict[str, Any]) -> dict[str, Any]:
    """Import window for a mailbox being connected or reconnected.

    A new mailbox imports from the chosen date. Reconnecting never narrows what was
    already imported: only an earlier date restarts the initial scan (messages already
    stored are skipped by their provider id), otherwise the stored window and scan
    progress are kept. Connections created before the choice existed scanned from
    January 1st.
    """
    scope = normalized_import_scope(flow.get("import_scope"))
    chosen = import_since(scope)
    if not existing:
        return {"import_scope": scope, "import_since": chosen, "restart_scan": True}
    stored = existing.get("import_since") or import_since(DEFAULT_IMPORT_SCOPE)
    if isinstance(stored, datetime):
        stored = stored.date()
    elif not isinstance(stored, date):
        stored = date.fromisoformat(str(stored)[:10])
    if chosen < stored:
        return {"import_scope": scope, "import_since": chosen, "restart_scan": True}
    return {"import_scope": existing.get("import_scope") or DEFAULT_IMPORT_SCOPE, "import_since": stored, "restart_scan": False}


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
    if result["already_completed"]:
        return {"status": "connected", "provider": result["provider"]}
    try:
        if result["provider"] == "gmail":
            gmail_service._after_gmail_connected(result["connection_id"])
        else:
            microsoft_mail.sync_connection(result["connection_id"], trigger="connect")
    except Exception as exc:
        # The mailbox is connected; the first sync can be retried with "Actualizar".
        logger.warning("First mail sync after connection failed provider=%s error=%s", result["provider"], type(exc).__name__)
    return {"status": "connected", "provider": result["provider"]}
