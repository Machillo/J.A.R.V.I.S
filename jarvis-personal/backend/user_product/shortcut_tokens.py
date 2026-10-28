"""The iOS Shortcuts token: a limited credential for background App Intents.

The Shortcuts automations (Transacción for Apple Pay, Mensaje for bank SMS) run the app's
App Intents in the background, without the app's session (the Supabase session lives behind
"when unlocked" Keychain access and its refresh token rotates). They use this token instead:

- issued by the backend (``secrets.token_urlsafe``), shown to the app once, stored here only as
  its SHA-256; the app keeps it in the Keychain;
- one active token per account: issuing again revokes the previous one; revocable (DELETE);
- bound to the account and workspace it was issued for; it stops working if the account is
  not active any more, its workspace changed, or the plan no longer includes the feature;
- its only permission is creating review candidates through ``shortcut_capture`` (the routes
  that accept it are public paths that check it themselves; no other route accepts it).

The identity is always the token's account, never a value of the request body. The token never
appears in logs, errors or analytics.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Any

from fastapi import HTTPException

from backend.auth import owner_role
from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.auth.saas import enrich_identity
from backend.auth.workspace_context import resolve_personal_workspace_context
from backend.core.database import get_connection

TOKEN_PREFIX = "dsc_"
FEATURE = "ios_shortcuts"
_TOKEN_SHAPE = re.compile(r"^dsc_[A-Za-z0-9_-]{40,64}$")
INVALID_TOKEN = "Activá Atajos de iPhone de nuevo en DINCR → Perfil."


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def link_status() -> dict[str, Any]:
    """Whether this account has an active Shortcuts token. A read."""
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT created_at FROM shortcut_tokens
               WHERE account_id=%s AND workspace_id=%s AND revoked_at IS NULL""",
            (account_id, workspace_id),
        ).fetchone()
    return {"status": "ok", "linked": bool(row), "created_at": row["created_at"] if row else None}


def issue_token() -> dict[str, Any]:
    """A new token for the session's account and workspace; the previous one stops working."""
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    with get_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"shortcut_token:{account_id}",))
        conn.execute(
            "UPDATE shortcut_tokens SET revoked_at=NOW() WHERE account_id=%s AND revoked_at IS NULL",
            (account_id,),
        )
        row = conn.execute(
            """INSERT INTO shortcut_tokens (account_id, workspace_id, token_hash)
               VALUES (%s, %s, %s) RETURNING created_at""",
            (account_id, workspace_id, token_hash(token)),
        ).fetchone()
        conn.commit()
    return {"status": "ok", "token": token, "created_at": row["created_at"]}


def revoke_token() -> dict[str, Any]:
    """Revoke the account's token (sign-out, account switch, "Desactivar"). Idempotent."""
    account_id = get_current_account_id()
    with get_connection() as conn:
        conn.execute(
            "UPDATE shortcut_tokens SET revoked_at=NOW() WHERE account_id=%s AND revoked_at IS NULL",
            (account_id,),
        )
        conn.commit()
    return {"status": "ok", "linked": False}


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail=INVALID_TOKEN)


def authenticate(authorization: str | None) -> dict[str, Any]:
    """The session-like identity of an active Shortcuts token (``Authorization: Bearer dsc_…``).

    Raises 401 for a missing, malformed, unknown or revoked token, or one whose account or
    workspace no longer matches. Never says which.
    """
    raw = str(authorization or "")
    token = raw[len("Bearer "):].strip() if raw.startswith("Bearer ") else ""
    if not _TOKEN_SHAPE.fullmatch(token):
        raise _unauthorized()
    digest = token_hash(token)
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id, account_id, workspace_id, token_hash FROM shortcut_tokens
               WHERE token_hash=%s AND revoked_at IS NULL""",
            (digest,),
        ).fetchone()
        if not row or not hmac.compare_digest(str(row["token_hash"]), digest):
            raise _unauthorized()
        # The account's own login record (auth bridge): same reads as a session's identity.
        account = conn.execute("SELECT legacy_allowed_user_id FROM accounts WHERE id=%s", (row["account_id"],)).fetchone()
        login_id = account and account.get("legacy_allowed_user_id")
        login = conn.execute(
            "SELECT email, role, status FROM allowed_users WHERE id=%s", (login_id,),
        ).fetchone() if login_id else None
        if not login or login["status"] != "active":
            raise _unauthorized()
        context = resolve_personal_workspace_context(conn, int(login_id))
        if str(context.get("account_id")) != str(row["account_id"]) or str(context.get("workspace_id")) != str(row["workspace_id"]):
            raise _unauthorized()
        try:
            role = owner_role.effective_role(login["role"], login["email"], account_ref=login_id)
        except HTTPException:
            raise _unauthorized() from None
        conn.execute("UPDATE shortcut_tokens SET last_used_at=NOW() WHERE id=%s", (row["id"],))
        conn.commit()
    return enrich_identity({
        "id": login_id,
        "email": login["email"],
        "role": role,
        "status": login["status"],
        **context,
    })
