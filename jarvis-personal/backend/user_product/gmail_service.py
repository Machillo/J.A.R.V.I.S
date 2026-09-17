from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from backend.auth.current_user import (
    get_current_account_id,
    get_current_user,
    get_current_workspace_id,
)
from backend.core.database import get_connection
from backend.email_monitor.parser import parse_financial_email
from backend.finance.category_catalog import normalize_category
from backend.user_product.service import _legacy_financial_user_id


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
FINVA_QUERY = os.getenv(
    "FINVA_GMAIL_QUERY",
    "(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr "
    "OR from:alerta@baccredomatic.com OR from:estadosdecuenta@baccredomatic.cr "
    "OR from:estadodecuenta@baccredomatic.cr OR from:info@info.baccredomatic.net "
    "OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com "
    "OR from:bancopopular.fi.cr) newer_than:45d -in:spam -in:trash",
)


def _google_config() -> tuple[str, str, str]:
    client_id = os.getenv("FINVA_GMAIL_CLIENT_ID") or os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("FINVA_GMAIL_CLIENT_SECRET") or os.getenv("GMAIL_CLIENT_SECRET")
    redirect_uri = os.getenv("FINVA_GMAIL_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="La conexión con Gmail todavía no está configurada en FINVA.",
        )
    return client_id, client_secret, redirect_uri


def _return_url(status: str) -> str:
    base = os.getenv("FINVA_GMAIL_RETURN_URL", "com.finva.app://gmail/callback").strip()
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'gmail': status})}"


def _state_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _vault_create(conn, token: str, account_id: str) -> str:
    row = conn.execute(
        "SELECT vault.create_secret(%s, NULL, %s) AS secret_id",
        (token, f"FINVA Gmail refresh token for account {account_id}"),
    ).fetchone()
    if not row or not row.get("secret_id"):
        raise RuntimeError("No se pudo proteger la autorización de Gmail.")
    return str(row["secret_id"])


def _vault_read(conn, secret_id: str) -> str:
    row = conn.execute(
        "SELECT decrypted_secret FROM vault.decrypted_secrets WHERE id=%s::uuid",
        (secret_id,),
    ).fetchone()
    if not row or not row.get("decrypted_secret"):
        raise RuntimeError("La autorización de Gmail no está disponible.")
    return str(row["decrypted_secret"])


def _vault_delete(conn, secret_id: str | None) -> None:
    if secret_id:
        conn.execute("DELETE FROM vault.secrets WHERE id=%s::uuid", (secret_id,))


def _credentials(refresh_token: str):
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError("El conector Gmail no está instalado.") from exc

    client_id, client_secret, _ = _google_config()
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[GMAIL_SCOPE],
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _mark_reconnect(connection_id: int, message: str = "Google solicitó reconectar Gmail.") -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE finva_gmail_connections
               SET status='reauthorization_required',last_error=%s,updated_at=NOW()
               WHERE id=%s""",
            (message, connection_id),
        )
        conn.commit()


def gmail_status() -> dict[str, Any]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id,google_email,status,granted_scopes,last_sync_at,last_success_at,
                      watch_expiration,last_error,connected_at,updated_at
               FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s""",
            (account_id, workspace_id),
        ).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) AS total FROM finva_email_candidates WHERE workspace_id=%s AND status='pending'",
            (workspace_id,),
        ).fetchone()
    if not row:
        return {"connected": False, "status": "disconnected", "pending": 0}
    data = dict(row)
    return {
        "connected": data.get("status") == "active",
        "needs_reauthorization": data.get("status") == "reauthorization_required",
        "automatic_updates": bool(data.get("watch_expiration")),
        "pending": int((pending or {}).get("total") or 0),
        **data,
    }


def begin_gmail_connection() -> dict[str, str]:
    client_id, _, redirect_uri = _google_config()
    user = get_current_user()
    # Gmail candidates ultimately write to legacy financial tables whose FK is
    # users.id, not allowed_users.id. They are different identity namespaces.
    legacy_user_id = _legacy_financial_user_id()
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    state = secrets.token_urlsafe(40)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    with get_connection() as conn:
        conn.execute("DELETE FROM finva_gmail_oauth_states WHERE expires_at<NOW() OR account_id=%s", (account_id,))
        conn.execute(
            """INSERT INTO finva_gmail_oauth_states(
                   state_hash,account_id,workspace_id,legacy_user_id,expires_at
               ) VALUES(%s,%s,%s,%s,%s)""",
            (_state_hash(state), account_id, workspace_id, legacy_user_id, expires_at),
        )
        conn.commit()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent select_account",
        "state": state,
        "login_hint": user.get("email") or "",
    }
    return {"authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


def finish_gmail_connection(code: str | None, state: str | None, error: str | None = None):
    if error or not code or not state:
        return RedirectResponse(_return_url("denied"), status_code=302)

    with get_connection() as conn:
        oauth_state = conn.execute(
            """SELECT account_id,workspace_id,legacy_user_id
               FROM finva_gmail_oauth_states
               WHERE state_hash=%s AND expires_at>NOW()
               FOR UPDATE""",
            (_state_hash(state),),
        ).fetchone()
        if not oauth_state:
            return RedirectResponse(_return_url("invalid_state"), status_code=302)

    client_id, client_secret, redirect_uri = _google_config()
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    if response.status_code != 200:
        return RedirectResponse(_return_url("exchange_failed"), status_code=302)
    tokens = response.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return RedirectResponse(_return_url("missing_refresh_token"), status_code=302)

    try:
        service = _credentials(refresh_token)
        profile = service.users().getProfile(userId="me").execute()
    except Exception:
        return RedirectResponse(_return_url("profile_failed"), status_code=302)
    google_email = str(profile.get("emailAddress") or "").strip().lower()
    if not google_email:
        return RedirectResponse(_return_url("profile_failed"), status_code=302)

    account_id = str(oauth_state["account_id"])
    workspace_id = str(oauth_state["workspace_id"])
    with get_connection() as conn:
        current = conn.execute(
            "SELECT refresh_token_secret_id FROM finva_gmail_connections WHERE account_id=%s FOR UPDATE",
            (account_id,),
        ).fetchone()
        secret_id = _vault_create(conn, refresh_token, account_id)
        row = conn.execute(
            """INSERT INTO finva_gmail_connections(
                   account_id,workspace_id,legacy_user_id,google_email,refresh_token_secret_id,
                   granted_scopes,status,connected_at,updated_at
               ) VALUES(%s,%s,%s,%s,%s::uuid,%s,'active',NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET
                   workspace_id=EXCLUDED.workspace_id,legacy_user_id=EXCLUDED.legacy_user_id,
                   google_email=EXCLUDED.google_email,refresh_token_secret_id=EXCLUDED.refresh_token_secret_id,
                   granted_scopes=EXCLUDED.granted_scopes,status='active',last_error=NULL,
                   connected_at=NOW(),updated_at=NOW()
               RETURNING id""",
            (account_id, workspace_id, int(oauth_state["legacy_user_id"]), google_email, secret_id, [GMAIL_SCOPE]),
        ).fetchone()
        old_secret = (current or {}).get("refresh_token_secret_id")
        if old_secret and str(old_secret) != secret_id:
            _vault_delete(conn, str(old_secret))
        conn.execute("DELETE FROM finva_gmail_oauth_states WHERE state_hash=%s", (_state_hash(state),))
        conn.commit()

    _start_watch(int(row["id"]), service, suppress_errors=True)
    try:
        _sync_connection(int(row["id"]), service=service, max_results=100)
    except Exception:
        pass
    return RedirectResponse(_return_url("connected"), status_code=302)


def disconnect_gmail() -> dict[str, str]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id,refresh_token_secret_id FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s FOR UPDATE""",
            (account_id, workspace_id),
        ).fetchone()
        if not row:
            return {"status": "disconnected"}
        try:
            token = _vault_read(conn, str(row["refresh_token_secret_id"]))
            requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10)
        except Exception:
            pass
        conn.execute("DELETE FROM finva_gmail_connections WHERE id=%s", (int(row["id"]),))
        _vault_delete(conn, str(row["refresh_token_secret_id"]))
        conn.commit()
    return {"status": "disconnected"}


def _decode_part(part: dict[str, Any]) -> str:
    data = (part.get("body") or {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return "\n".join(_decode_part(child) for child in (part.get("parts") or []))


def _plain_text(payload: dict[str, Any]) -> str:
    raw = _decode_part(payload)
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _adapt_identity(value: str, display_name: str) -> str:
    adapted = value or ""
    names = [display_name.strip(), display_name.strip().split(" ")[0] if display_name.strip() else ""]
    for name in sorted({item for item in names if len(item) >= 3}, key=len, reverse=True):
        adapted = re.sub(re.escape(name), "Kenneth", adapted, flags=re.I)
    return adapted


def _process_message(service, connection: dict[str, Any], message_id: str) -> str:
    full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {item.get("name", "").lower(): item.get("value", "") for item in full.get("payload", {}).get("headers", [])}
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    body = _plain_text(full.get("payload") or {}) or full.get("snippet", "")
    received_at = None
    if headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc).isoformat()
        except Exception:
            received_at = None

    display_name = str(connection.get("display_name") or "")
    parsed = parse_financial_email(
        _adapt_identity(subject, display_name),
        sender,
        _adapt_identity(body, display_name),
        received_at,
    )
    kind = str(parsed.get("email_kind") or "ignored")
    confidence = float(parsed.get("confidence") or 0)
    status = "ignored"
    transaction_id = None

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM finva_email_messages WHERE connection_id=%s AND provider_message_id=%s",
            (int(connection["id"]), message_id),
        ).fetchone()
        if existing:
            return "duplicate"
        email_row = conn.execute(
            """INSERT INTO finva_email_messages(
                   connection_id,account_id,workspace_id,provider_message_id,sender,subject,received_at,
                   bank,status,parse_reason
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                int(connection["id"]), connection["account_id"], connection["workspace_id"], message_id,
                sender[:500], subject[:500], received_at, parsed.get("bank") or "unknown", kind,
                parsed.get("confidence_reason") or parsed.get("ignore_reason") or "",
            ),
        ).fetchone()

        if kind == "movement" and parsed.get("amount") and parsed.get("transaction_type"):
            tx_type = str(parsed.get("transaction_type"))
            candidate_status = "pending"
            if confidence >= 0.97 and tx_type in {"income", "expense", "debt_payment"}:
                category = normalize_category(parsed.get("category"), tx_type)
                tx = conn.execute(
                    """INSERT INTO transactions(
                           transaction_date,description,amount,transaction_type,category,account,source,notes,
                           original_amount,original_currency,exchange_rate,user_id,workspace_id,created_at
                       ) VALUES(%s,%s,%s,%s,%s,%s,'finva_gmail',%s,%s,%s,%s,%s,%s,NOW())
                       RETURNING id""",
                    (
                        parsed.get("transaction_date") or datetime.now(timezone.utc).date().isoformat(),
                        str(parsed.get("description") or subject)[:500], parsed.get("amount"), tx_type, category,
                        str(parsed.get("account") or "")[:200], "Importado automáticamente desde Gmail.",
                        parsed.get("original_amount"), parsed.get("original_currency"), parsed.get("exchange_rate"),
                        int(connection["legacy_user_id"]), connection["workspace_id"],
                    ),
                ).fetchone()
                transaction_id = int(tx["id"])
                candidate_status = "auto_saved"
            conn.execute(
                """INSERT INTO finva_email_candidates(
                       email_message_id,account_id,workspace_id,transaction_id,transaction_date,description,
                       amount,transaction_type,category,bank,confidence,status,raw_payload
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (
                    int(email_row["id"]), connection["account_id"], connection["workspace_id"], transaction_id,
                    parsed.get("transaction_date") or datetime.now(timezone.utc).date().isoformat(),
                    str(parsed.get("description") or subject)[:500], parsed.get("amount"), tx_type,
                    normalize_category(parsed.get("category"), tx_type), parsed.get("bank") or "unknown",
                    confidence, candidate_status, json.dumps(parsed, default=str),
                ),
            )
            status = candidate_status
            conn.execute("UPDATE finva_email_messages SET status=%s WHERE id=%s", (status, int(email_row["id"])))
        conn.commit()
    return status


def _connection_with_token(connection_id: int) -> tuple[dict[str, Any], str]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT c.*,a.display_name FROM finva_gmail_connections c
               JOIN accounts a ON a.id=c.account_id WHERE c.id=%s""",
            (connection_id,),
        ).fetchone()
        if not row:
            raise RuntimeError("Conexión Gmail no encontrada.")
        token = _vault_read(conn, str(row["refresh_token_secret_id"]))
    return dict(row), token


def _sync_connection(connection_id: int, service=None, max_results: int = 100) -> dict[str, Any]:
    connection, token = _connection_with_token(connection_id)
    try:
        service = service or _credentials(token)
        response = service.users().messages().list(
            userId="me", q=FINVA_QUERY, maxResults=max(1, min(max_results, 250))
        ).execute()
        results = [_process_message(service, connection, item["id"]) for item in response.get("messages", []) if item.get("id")]
    except Exception as exc:
        message = str(exc).lower()
        if "invalid_grant" in message or "token has been expired" in message or "revoked" in message:
            _mark_reconnect(connection_id)
            raise HTTPException(status_code=409, detail="La conexión de Gmail venció. Volvé a autorizarla desde FINVA.") from exc
        with get_connection() as conn:
            conn.execute(
                "UPDATE finva_gmail_connections SET last_sync_at=NOW(),last_error=%s,updated_at=NOW() WHERE id=%s",
                ("No se pudo completar la sincronización.", connection_id),
            )
            conn.commit()
        raise

    with get_connection() as conn:
        conn.execute(
            """UPDATE finva_gmail_connections SET status='active',last_sync_at=NOW(),last_success_at=NOW(),
                      last_error=NULL,updated_at=NOW() WHERE id=%s""",
            (connection_id,),
        )
        conn.commit()
    return {
        "status": "ok",
        "found": len(results),
        "auto_saved": results.count("auto_saved"),
        "pending": results.count("pending"),
        "duplicates": results.count("duplicate"),
    }


def sync_current_gmail() -> dict[str, Any]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM finva_gmail_connections WHERE account_id=%s AND workspace_id=%s",
            (account_id, workspace_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Primero conectá Gmail.")
    return _sync_connection(int(row["id"]))


def _start_watch(connection_id: int, service, suppress_errors: bool = False) -> None:
    topic = os.getenv("FINVA_GMAIL_PUBSUB_TOPIC", "").strip()
    if not topic:
        return
    try:
        response = service.users().watch(
            userId="me", body={"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"}
        ).execute()
        expiration_ms = int(response.get("expiration") or 0)
        expiration = datetime.fromtimestamp(expiration_ms / 1000, timezone.utc) if expiration_ms else None
        with get_connection() as conn:
            conn.execute(
                """UPDATE finva_gmail_connections SET history_id=%s,watch_expiration=%s,
                          last_error=NULL,updated_at=NOW() WHERE id=%s""",
                (str(response.get("historyId") or ""), expiration, connection_id),
            )
            conn.commit()
    except Exception:
        if not suppress_errors:
            raise


def gmail_maintenance(secret: str | None) -> dict[str, Any]:
    expected = os.getenv("FINVA_GMAIL_CRON_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="FINVA_GMAIL_CRON_SECRET no está configurado.")
    if not secret or not secrets.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="Secreto de mantenimiento inválido.")
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM finva_gmail_connections WHERE status='active' ORDER BY id").fetchall()
    completed = 0
    reconnect = 0
    for row in rows:
        connection_id = int(row["id"])
        try:
            _, token = _connection_with_token(connection_id)
            service = _credentials(token)
            _start_watch(connection_id, service, suppress_errors=True)
            _sync_connection(connection_id, service=service, max_results=100)
            completed += 1
        except HTTPException as exc:
            if exc.status_code == 409:
                reconnect += 1
        except Exception:
            continue
    return {"status": "ok", "connections": len(rows), "completed": completed, "reconnect": reconnect}


def process_gmail_push(payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    expected = os.getenv("FINVA_GMAIL_PUBSUB_VERIFICATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Verificación Pub/Sub no configurada.")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Notificación no autorizada.")
    encoded = (payload.get("message") or {}).get("data")
    if not encoded:
        raise HTTPException(status_code=400, detail="Notificación incompleta.")
    try:
        notification = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Notificación inválida.") from exc
    email = str(notification.get("emailAddress") or "").lower()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM finva_gmail_connections WHERE google_email=%s AND status='active'",
            (email,),
        ).fetchone()
    if not row:
        return {"status": "ignored"}
    result = _sync_connection(int(row["id"]), max_results=50)
    return {"status": "ok", **result}
