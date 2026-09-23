from __future__ import annotations

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection


GMAIL_CONSENT_VERSION = "mail-monitor-2026-09-v2"


def _status(conn, account_id: str, workspace_id: str) -> dict:
    row = conn.execute(
        """SELECT accepted_at
             FROM finva_gmail_consents
            WHERE account_id=%s AND workspace_id=%s AND consent_version=%s
              AND revoked_at IS NULL
            LIMIT 1""",
        (account_id, workspace_id, GMAIL_CONSENT_VERSION),
    ).fetchone()
    return {
        "required": row is None,
        "version": GMAIL_CONSENT_VERSION,
        "accepted_at": (row or {}).get("accepted_at"),
    }


def gmail_consent_status() -> dict:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        return _status(conn, account_id, workspace_id)


def accept_gmail_consent(*, accepted: bool, version: str) -> dict:
    if not accepted:
        raise HTTPException(status_code=422, detail="Debés aceptar el uso de Email Monitor para conectarlo.")
    if version != GMAIL_CONSENT_VERSION:
        raise HTTPException(status_code=409, detail="La explicación de Email Monitor cambió. Revisá la versión vigente.")
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO finva_gmail_consents(account_id,workspace_id,consent_version,accepted_at)
               VALUES(%s,%s,%s,NOW())
               ON CONFLICT(account_id,workspace_id,consent_version)
               DO UPDATE SET accepted_at=NOW(),revoked_at=NULL""",
            (account_id, workspace_id, GMAIL_CONSENT_VERSION),
        )
        conn.commit()
        return {"status": "accepted", **_status(conn, account_id, workspace_id)}


def require_gmail_consent() -> None:
    status = gmail_consent_status()
    if status["required"]:
        raise HTTPException(status_code=409, detail="Aceptá la explicación y privacidad de Email Monitor antes de conectar un buzón.")
