"""Read authorized Outlook/Hotmail inboxes through Microsoft Graph.

The existing DINCR candidate pipeline owns parsing, review and retention.
Microsoft credentials remain in Supabase Vault and never reach the client.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote, urlencode, urlparse

import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.user_product.gmail_consent import require_gmail_consent
from backend.user_product.gmail_service import (
    DINCR_QUERY, _financial_user_id_for_account, _has_active_vip_access,
    _ingest_message, _vault_create, _vault_delete, _vault_read,
)

SCOPE = "offline_access User.Read Mail.Read"
AUTHORITY = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"
ALLOWED_SENDERS = frozenset(re.findall(r"from:([\w@.\-]+)", DINCR_QUERY, flags=re.I)) | {"ccss.sa.cr"}


def _config() -> tuple[str, str, str]:
    values = tuple(os.getenv(name, "").strip() for name in (
        "DINCR_MICROSOFT_CLIENT_ID", "DINCR_MICROSOFT_CLIENT_SECRET", "DINCR_MICROSOFT_REDIRECT_URI",
    ))
    if not all(values):
        raise HTTPException(status_code=503, detail="Outlook todavía no está configurado en DINCR.")
    return values


def _state(account_id: str, workspace_id: str) -> str:
    payload = {"a": account_id, "w": workspace_id,
               "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
               "nonce": secrets.token_urlsafe(20)}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(_config()[1].encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_state(value: str | None) -> dict | None:
    try:
        encoded, signature = (value or "").rsplit(".", 1)
        expected = hmac.new(_config()[1].encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["exp"] < datetime.now(timezone.utc).timestamp() or not payload["a"] or not payload["w"]:
            return None
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _return_url(status: str) -> str:
    base = os.getenv("DINCR_GMAIL_RETURN_URL", "com.dincr.app://gmail/callback").strip()
    return f"{base}{'&' if '?' in base else '?'}{urlencode({'microsoft': status})}"


def begin_connection() -> dict[str, str]:
    require_gmail_consent()
    client_id, _, redirect_uri = _config()
    params = {"client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
              "response_mode": "query", "scope": SCOPE, "prompt": "select_account",
              "state": _state(get_current_account_id(), get_current_workspace_id())}
    return {"authorization_url": f"{AUTHORITY}/authorize?{urlencode(params)}"}


def _graph_get(token: str, path: str, params: dict | None = None) -> dict:
    url = path if path.startswith("https://") else GRAPH + path
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "graph.microsoft.com"
            or (not parsed.path.startswith("/v1.0/me/") and parsed.path != "/v1.0/me")):
        raise ValueError("Página de correo no permitida.")
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params,
                            timeout=20, allow_redirects=False)
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise ValueError("Respuesta inesperada del proveedor de correo.")
    return response.json()


def finish_connection(code: str | None, state: str | None, error: str | None = None):
    if error or not code:
        return RedirectResponse(_return_url("denied"), status_code=302)
    payload = _verify_state(state)
    if not payload:
        return RedirectResponse(_return_url("invalid_state"), status_code=302)
    account_id, workspace_id = payload["a"], payload["w"]
    with get_connection() as conn:
        if not _has_active_vip_access(conn, account_id):
            return RedirectResponse(_return_url("vip_required"), status_code=302)
    client_id, client_secret, redirect_uri = _config()
    try:
        response = requests.post(f"{AUTHORITY}/token", data={
            "client_id": client_id, "client_secret": client_secret, "code": code,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "scope": SCOPE,
        }, timeout=20)
        response.raise_for_status()
        tokens = response.json()
        if not tokens.get("refresh_token") or "Mail.Read" not in tokens.get("scope", "").split():
            return RedirectResponse(_return_url("permission_missing"), status_code=302)
        profile = _graph_get(tokens["access_token"], "/me")
        address = str(profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
        if not address or "@" not in address:
            return RedirectResponse(_return_url("mailbox_missing"), status_code=302)
        _graph_get(tokens["access_token"], "/me/messages", {"$top": "1", "$select": "id"})
    except (requests.RequestException, ValueError, KeyError):
        return RedirectResponse(_return_url("mailbox_unavailable"), status_code=302)
    legacy_user_id = _financial_user_id_for_account(account_id)
    with get_connection() as conn:
        if not _has_active_vip_access(conn, account_id):
            return RedirectResponse(_return_url("vip_required"), status_code=302)
        existing = conn.execute(
            """SELECT id,refresh_token_secret_id,granted_scopes FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s AND lower(google_email)=%s FOR UPDATE""",
            (account_id, workspace_id, address),
        ).fetchone()
        if existing and "Mail.Read" not in (existing.get("granted_scopes") or []):
            return RedirectResponse(_return_url("already_connected_elsewhere"), status_code=302)
        secret_id = _vault_create(conn, tokens["refresh_token"], account_id, "Microsoft")
        if existing:
            row = conn.execute(
                """UPDATE finva_gmail_connections SET legacy_user_id=%s,
                     refresh_token_secret_id=%s::uuid,granted_scopes=%s,
                     status='active',last_error=NULL,connected_at=NOW(),updated_at=NOW()
                   WHERE id=%s RETURNING id""",
                (legacy_user_id, secret_id, ["Mail.Read"], existing["id"]),
            ).fetchone()
            _vault_delete(conn, str(existing["refresh_token_secret_id"]))
        else:
            row = conn.execute(
                """INSERT INTO finva_gmail_connections(
                       account_id,workspace_id,legacy_user_id,google_email,refresh_token_secret_id,
                       granted_scopes,status,connected_at,updated_at)
                   VALUES(%s,%s,%s,%s,%s::uuid,%s,'active',NOW(),NOW()) RETURNING id""",
                (account_id, workspace_id, legacy_user_id, address, secret_id, ["Mail.Read"]),
            ).fetchone()
        conn.commit()
    try:
        sync_connection(int(row["id"]))
    except Exception:
        pass  # Connection remains available for an explicit retry.
    return RedirectResponse(_return_url("connected"), status_code=302)


def _refresh(connection: dict, refresh_token: str) -> str:
    client_id, client_secret, _ = _config()
    response = requests.post(f"{AUTHORITY}/token", data={
        "client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
        "grant_type": "refresh_token", "scope": SCOPE,
    }, timeout=20)
    if response.status_code in {400, 401}:
        with get_connection() as conn:
            conn.execute("UPDATE finva_gmail_connections SET status='reauthorization_required' WHERE id=%s", (connection["id"],))
            conn.commit()
        raise HTTPException(status_code=409, detail="Outlook requiere volver a autorizar el correo.")
    response.raise_for_status()
    tokens = response.json()
    if tokens.get("refresh_token") and tokens["refresh_token"] != refresh_token:
        with get_connection() as conn:
            # Another sync could rotate a token concurrently: only replace the one we used.
            current = conn.execute(
                "SELECT refresh_token_secret_id FROM finva_gmail_connections WHERE id=%s FOR UPDATE",
                (connection["id"],),
            ).fetchone()
            if current and str(current["refresh_token_secret_id"]) == str(connection["refresh_token_secret_id"]):
                replacement = _vault_create(conn, tokens["refresh_token"], str(connection["account_id"]), "Microsoft")
                conn.execute("UPDATE finva_gmail_connections SET refresh_token_secret_id=%s::uuid WHERE id=%s",
                             (replacement, connection["id"]))
                _vault_delete(conn, str(connection["refresh_token_secret_id"]))
                conn.commit()
    return tokens["access_token"]


def _sender_allowed(value: str) -> bool:
    # Graph supplies from.emailAddress.address, not an RFC 5322 display string.
    # Reject decorated or malformed values to prevent a forged display name
    # from impersonating an approved bank sender.
    sender = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.+\-]+@[a-z0-9.\-]+", sender):
        return False
    domain = sender.rsplit("@", 1)[-1]
    return bool(sender and "@" in sender and any(
        sender == allowed or domain == allowed or domain.endswith("." + allowed)
        for allowed in ALLOWED_SENDERS
    ))


def _message_text(value: str) -> str:
    clean = re.sub(r"<script.*?</script>|<style.*?</style>", " ", value or "", flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", clean))).strip()


def _attachments(token: str, message_id: str) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    names, texts = [], []
    page = f"/me/messages/{quote(message_id, safe='')}/attachments"
    while page:
        response = _graph_get(token, page, {"$top": "25"} if page.startswith("/") else None)
        for attachment in response.get("value", []):
            filename = str(attachment.get("name") or "")[:255]
            if filename:
                names.append(filename)
            if not filename.lower().endswith(".pdf") or int(attachment.get("size") or 0) > 10_000_000:
                continue
            encoded = attachment.get("contentBytes")
            if not encoded:
                attachment = _graph_get(token, f"/me/messages/{quote(message_id, safe='')}/attachments/{quote(attachment['id'], safe='')}")
                encoded = attachment.get("contentBytes")
            if encoded and len(encoded) < 14_000_000:
                try:
                    reader = PdfReader(BytesIO(base64.b64decode(encoded, validate=True)))
                    text = "\n".join((item.extract_text() or "") for item in reader.pages[:8]).strip()
                    if text:
                        texts.append(f"[PDF {filename}]\n{text}")
                except Exception:
                    continue
        page = response.get("@odata.nextLink")
    return "\n".join(texts), names


def sync_connection(connection_id: int, max_results: int = 100) -> dict:
    with get_connection() as conn:
        connection = conn.execute(
            """SELECT c.*,a.display_name FROM finva_gmail_connections c
               JOIN accounts a ON a.id=c.account_id WHERE c.id=%s""", (connection_id,),
        ).fetchone()
        if not connection or "Mail.Read" not in (connection.get("granted_scopes") or []):
            raise HTTPException(status_code=404, detail="Conexión de Outlook no encontrada.")
        if not _has_active_vip_access(conn, str(connection["account_id"])):
            raise HTTPException(status_code=403, detail="La lectura de correo requiere VIP.")
        token = _vault_read(conn, str(connection["refresh_token_secret_id"]))
    connection = dict(connection)
    access_token = _refresh(connection, token)
    initial = not connection.get("initial_scan_completed_at")
    since = date.today().replace(month=1, day=1) if initial else date.today() - timedelta(days=45)
    results = []
    page = connection.get("initial_scan_page_token") if initial else None
    max_pages = 1 if initial else 10
    for _ in range(max_pages):
        response = _graph_get(access_token, page or "/me/messages", None if page else {
            "$filter": f"receivedDateTime ge {since:%Y-%m-%d}T00:00:00Z",
            "$select": "id,from,receivedDateTime",
            "$top": "50", "$orderby": "receivedDateTime desc",
        })
        for message in response.get("value", []):
            message_id = message.get("id")
            sender = ((message.get("from") or {}).get("emailAddress") or {}).get("address", "")
            if not message_id or not _sender_allowed(sender):
                continue
            try:
                full = _graph_get(access_token, f"/me/messages/{quote(message_id, safe='')}", {
                    "$select": "id,subject,from,receivedDateTime,body,hasAttachments",
                })
                attachment_text, names = _attachments(access_token, message_id) if full.get("hasAttachments") else ("", [])
                results.append(_ingest_message(
                    connection, message_id, subject=full.get("subject") or "", sender=sender,
                    body=_message_text((full.get("body") or {}).get("content") or ""),
                    attachment_text=attachment_text, attachment_names=names,
                    received_at=full.get("receivedDateTime"),
                ))
            except Exception:
                raise  # Preserve the scan cursor so a failed message is retried.
        page = response.get("@odata.nextLink")
        if not page or initial or len(results) >= max_results:
            break
    with get_connection() as conn:
        conn.execute(
            """UPDATE finva_gmail_connections SET last_sync_at=NOW(),last_success_at=NOW(),
                 last_error=NULL,initial_scan_page_token=%s,
                 initial_scan_started_at=COALESCE(initial_scan_started_at,NOW()),
                 initial_scan_completed_at=CASE WHEN %s THEN NOW() ELSE initial_scan_completed_at END,
                 updated_at=NOW() WHERE id=%s""", (page if initial else None, initial and not page, connection_id),
        )
        conn.commit()
    return {"status": "ok", "scan_scope": "year_to_date" if initial else "recent",
            "initial_scan_complete": not initial or not page, "found": len(results),
            "auto_saved": results.count("auto_saved"), "pending": results.count("pending"),
            "payroll_reports": results.count("payroll_statement"), "duplicates": results.count("duplicate")}
