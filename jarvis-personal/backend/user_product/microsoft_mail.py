"""Read authorized Outlook/Hotmail inboxes through Microsoft Graph.

The existing DINCR candidate pipeline owns parsing, review and retention.
Microsoft credentials remain in Supabase Vault and never reach the client.
"""

from __future__ import annotations

import base64
import html
import logging
import os
import re
import secrets
from datetime import date, timedelta
from io import BytesIO
from urllib.parse import quote, urlencode, urlparse

import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from backend.core.database import get_connection
from backend.user_product import mail_oauth
from backend.user_product.gmail_consent import require_gmail_consent
from backend.user_product.gmail_service import (
    FINVA_QUERY, _has_active_vip_access,
    _ingest_message, _vault_create, _vault_delete, _vault_read,
)

logger = logging.getLogger(__name__)

# offline_access is required for a refresh token (background and later syncs).
# Mail.Read is read-only; DINCR never requests Mail.ReadWrite or Mail.Send.
SCOPE = "offline_access User.Read Mail.Read"
REQUIRED_SCOPE = "mail.read"
# "common" accepts personal Microsoft accounts (Outlook.com, Hotmail, Live) and
# work/school accounts, matching the multitenant + personal app registration.
AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE_PREFIX = "https://graph.microsoft.com/"
ALLOWED_SENDERS = frozenset(re.findall(r"from:([\w@.\-]+)", FINVA_QUERY, flags=re.I)) | {"ccss.sa.cr"}

# Render names first; the legacy FINVA_MICROSOFT_* names keep working.
CONFIG_NAMES = (
    ("MICROSOFT_CLIENT_ID", "FINVA_MICROSOFT_CLIENT_ID"),
    ("MICROSOFT_CLIENT_SECRET", "FINVA_MICROSOFT_CLIENT_SECRET"),
    ("MICROSOFT_REDIRECT_URI", "FINVA_MICROSOFT_REDIRECT_URI"),
)


def _config_values() -> tuple[str, str, str]:
    return tuple(
        next((value for value in (os.getenv(name, "").strip() for name in names) if value), "")
        for names in CONFIG_NAMES
    )


def microsoft_configured() -> bool:
    return all(_config_values())


def _config() -> tuple[str, str, str]:
    values = _config_values()
    if not all(values):
        raise HTTPException(status_code=503, detail="Outlook todavía no está configurado en DINCR.")
    return values


def _granted_scopes(value: str | None) -> set[str]:
    """Microsoft may return Graph scopes fully qualified and in any case."""
    return {
        item.lower().removeprefix(GRAPH_SCOPE_PREFIX)
        for item in str(value or "").split()
    }


def _return_url(status: str, **extra: str) -> str:
    base = os.getenv("FINVA_GMAIL_RETURN_URL", "com.finva.app://gmail/callback").strip()
    # ret identifies this response so the app handles each delivery once.
    return f"{base}{'&' if '?' in base else '?'}{urlencode({'microsoft': status, **extra, 'ret': secrets.token_urlsafe(8)})}"


def begin_connection() -> dict[str, str]:
    require_gmail_consent()
    client_id, _, redirect_uri = _config()
    state, code_challenge = mail_oauth.start_flow("microsoft")
    params = {"client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri,
              "response_mode": "query", "scope": SCOPE, "prompt": "select_account",
              "state": state, "code_challenge": code_challenge, "code_challenge_method": "S256"}
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
    """OAuth callback (public). Parks the refresh token; the app completes the link."""
    flow = mail_oauth.claim_callback("microsoft", state)
    if not flow:
        status = mail_oauth.rejected_callback_status("microsoft", state)
        logger.warning("Outlook authorization rejected: %s", "state already processed" if status == "already_processed" else "unknown, failed or expired state")
        return RedirectResponse(_return_url(status), status_code=302)
    if error or not code:
        # Only Microsoft's error code (e.g. access_denied, consent_required) is
        # logged; error_description can echo tenant or account details.
        logger.warning("Outlook authorization not completed error=%s", str(error or "missing_code")[:60])
        mail_oauth.fail_flow(flow["id"])
        return RedirectResponse(_return_url("denied"), status_code=302)

    def failed(status: str) -> RedirectResponse:
        mail_oauth.fail_flow(flow["id"])
        return RedirectResponse(_return_url(status), status_code=302)

    account_id = str(flow["account_id"])
    with get_connection() as conn:
        if not _has_active_vip_access(conn, account_id):
            return failed("vip_required")
    client_id, client_secret, redirect_uri = _config()
    try:
        response = requests.post(f"{AUTHORITY}/token", data={
            "client_id": client_id, "client_secret": client_secret, "code": code,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "scope": SCOPE,
            "code_verifier": flow["code_verifier"],
        }, timeout=20)
        if response.status_code != 200:
            logger.warning("Outlook token exchange failed status=%s", response.status_code)
            return failed("exchange_failed")
        tokens = response.json()
        if not tokens.get("refresh_token") or REQUIRED_SCOPE not in _granted_scopes(tokens.get("scope")):
            logger.warning("Outlook authorization missing Mail.Read or offline access")
            return failed("permission_missing")
        profile = _graph_get(tokens["access_token"], "/me")
        address = str(profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
        if not address or "@" not in address:
            return failed("mailbox_missing")
        _graph_get(tokens["access_token"], "/me/messages", {"$top": "1", "$select": "id"})
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Outlook mailbox validation failed error=%s status=%s", type(exc).__name__,
                       getattr(getattr(exc, "response", None), "status_code", None))
        return failed("mailbox_unavailable")
    with get_connection() as conn:
        secret_id = _vault_create(conn, tokens["refresh_token"], account_id, "Microsoft")
        completion = mail_oauth.authorize_flow(conn, flow["id"], secret_id=secret_id, mailbox=address, scopes=["Mail.Read"])
        conn.commit()
    return RedirectResponse(_return_url("authorized", flow=str(flow["id"]), completion=completion), status_code=302)


def _attach_microsoft_connection(conn, flow: dict, legacy_user_id: int) -> int:
    """Attach an authorized Outlook flow to its account/workspace (caller commits)."""
    if flow["provider"] != "microsoft" or "Mail.Read" not in (flow.get("granted_scopes") or []):
        raise HTTPException(status_code=409, detail="La autorización no corresponde a Outlook. Volvé a conectarlo.")
    account_id, workspace_id = str(flow["account_id"]), str(flow["workspace_id"])
    if not _has_active_vip_access(conn, account_id):
        raise HTTPException(status_code=403, detail="Conectar un correo requiere el plan VIP activo.")
    address = str(flow["mailbox_address"])
    secret_id = str(flow["pending_secret_id"])
    existing = conn.execute(
        """SELECT id,refresh_token_secret_id,granted_scopes FROM finva_gmail_connections
           WHERE account_id=%s AND workspace_id=%s AND lower(google_email)=%s FOR UPDATE""",
        (account_id, workspace_id, address),
    ).fetchone()
    if existing and "Mail.Read" not in (existing.get("granted_scopes") or []):
        raise HTTPException(status_code=409, detail="Ese correo ya está conectado de otra forma en DINCR.")
    if existing:
        row = conn.execute(
            """UPDATE finva_gmail_connections SET legacy_user_id=%s,
                 refresh_token_secret_id=%s::uuid,granted_scopes=%s,
                 status='active',last_error=NULL,connected_at=NOW(),updated_at=NOW()
               WHERE id=%s RETURNING id""",
            (legacy_user_id, secret_id, ["Mail.Read"], existing["id"]),
        ).fetchone()
        if existing.get("refresh_token_secret_id") and str(existing["refresh_token_secret_id"]) != secret_id:
            _vault_delete(conn, str(existing["refresh_token_secret_id"]))
    else:
        row = conn.execute(
            """INSERT INTO finva_gmail_connections(
                   account_id,workspace_id,legacy_user_id,google_email,refresh_token_secret_id,
                   granted_scopes,status,connected_at,updated_at)
               VALUES(%s,%s,%s,%s,%s::uuid,%s,'active',NOW(),NOW()) RETURNING id""",
            (account_id, workspace_id, legacy_user_id, address, secret_id, ["Mail.Read"]),
        ).fetchone()
    return int(row["id"])


def _refresh(connection: dict, refresh_token: str) -> str:
    client_id, client_secret, _ = _config()
    response = requests.post(f"{AUTHORITY}/token", data={
        "client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
        "grant_type": "refresh_token", "scope": SCOPE,
    }, timeout=20)
    if response.status_code in {400, 401}:
        try:
            error_code = str(response.json().get("error") or "")[:60]
        except ValueError:
            error_code = ""
        logger.warning("Outlook token refresh rejected connection_id=%s status=%s error=%s",
                       connection["id"], response.status_code, error_code)
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
