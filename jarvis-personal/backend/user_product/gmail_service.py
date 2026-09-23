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
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from backend.auth.current_user import (
    get_current_account_id,
    get_current_workspace_id,
)
from backend.core.database import get_connection
from backend.email_monitor.parser import parse_financial_email
from backend.email_monitor.popular_pdf import parse_popular_email_document
from backend.email_monitor.payroll_statement import parse_ccss_order_patronal
from backend.email_monitor.gmail_content import collect_attachments, extract_pdf_attachment_text
from backend.finance.category_catalog import normalize_category
from backend.user_product.financial_candidate import canonical_candidate
from backend.user_product.financial_identity import discover_candidate_account
from backend.user_product.candidate_resolution import resolve_candidate, reevaluate_workspace_candidates
from backend.user_product.gmail_consent import gmail_consent_status, require_gmail_consent
from backend.user_product.gmail_retention import apply_gmail_retention, retention_policy
from backend.user_product.payroll_income import identify_received_payroll, link_received_payroll
from backend.user_product.statement_candidate import (
    PARSER_NAME as STATEMENT_PARSER_NAME,
    PARSER_VERSION as STATEMENT_PARSER_VERSION,
    parse_statement_movements,
    statement_candidate,
    statement_hash,
)


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DINCR_QUERY = os.getenv(
    "DINCR_GMAIL_QUERY",
    "(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr "
    "OR from:alerta@baccredomatic.com OR from:estadosdecuenta@baccredomatic.cr "
    "OR from:estadodecuenta@baccredomatic.cr OR from:info@info.baccredomatic.net "
    "OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com "
    "OR from:bancopopular.fi.cr OR from:bancopopularinforma.fi.cr OR from:bpdc.fi.cr) "
    "newer_than:45d -in:spam -in:trash",
)


def _year_to_date_query(as_of: date | None = None) -> str:
    """Use the current calendar year only for a connection's first sync."""
    current = as_of or date.today()
    query = re.sub(r"\s+newer_than:\d+d\b", "", DINCR_QUERY, flags=re.IGNORECASE)
    return f"{query} after:{current.year}/01/01"


def _list_message_refs(service, query: str, limit: int) -> list[dict[str, Any]]:
    """Page through a bounded Gmail search without retaining message content."""
    items: list[dict[str, Any]] = []
    page_token = None
    bounded_limit = max(1, min(int(limit), 1000))
    while len(items) < bounded_limit:
        request = {
            "userId": "me", "q": query,
            "maxResults": min(250, bounded_limit - len(items)),
        }
        if page_token:
            request["pageToken"] = page_token
        response = service.users().messages().list(**request).execute()
        items.extend(item for item in response.get("messages", []) if item.get("id"))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return items[:bounded_limit]


def _list_message_page(service, query: str, *, page_token: str | None, limit: int = 50) -> tuple[list[dict[str, Any]], str | None]:
    request: dict[str, Any] = {
        "userId": "me", "q": query, "maxResults": max(1, min(int(limit), 100)),
    }
    if page_token:
        request["pageToken"] = page_token
    response = service.users().messages().list(**request).execute()
    items = [item for item in response.get("messages", []) if item.get("id")]
    return items, response.get("nextPageToken")


def _aguinaldo_gmail_query(as_of: date | None = None) -> str:
    """Search the complete Costa Rican aguinaldo period for CCSS payroll orders."""
    current = as_of or date.today()
    period_start = date(current.year if current.month == 12 else current.year - 1, 12, 1)
    return (
        '(from:noreply@ccss.sa.cr OR from:ccss@ccss.sa.cr '
        'OR subject:"Generación de Orden Patronal Digital") '
        f'after:{period_start:%Y/%m/%d} -in:spam -in:trash'
    )

def _has_active_vip_access(conn, account_id: str) -> bool:
    """Return whether an account may use DINCR's Gmail automation.

    Interactive routes enforce the same entitlement through ``require_feature``.
    This database-level check also protects OAuth callbacks, Pub/Sub delivery and
    maintenance jobs, where no authenticated user context exists.
    """
    row = conn.execute(
        """SELECT 1
           FROM account_subscriptions s
           JOIN plans p ON p.id=s.plan_id
           WHERE s.account_id=%s
             AND s.status='active'
             AND p.code='vip'
             AND (
               s.access_source<>'courtesy'
               OR (s.expires_at IS NOT NULL AND s.expires_at>NOW())
             )
           LIMIT 1""",
        (account_id,),
    ).fetchone()
    return bool(row)


def _google_config() -> tuple[str, str, str]:
    client_id = os.getenv("DINCR_GMAIL_CLIENT_ID") or os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("DINCR_GMAIL_CLIENT_SECRET") or os.getenv("GMAIL_CLIENT_SECRET")
    redirect_uri = os.getenv("DINCR_GMAIL_REDIRECT_URI", "").strip()
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="La conexión con Gmail todavía no está configurada en DINCR.",
        )
    return client_id, client_secret, redirect_uri


def _return_url(status: str) -> str:
    base = os.getenv("DINCR_GMAIL_RETURN_URL", "com.dincr.app://gmail/callback").strip()
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'gmail': status})}"


def _oauth_state_key() -> bytes:
    _, client_secret, _ = _google_config()
    return client_secret.encode("utf-8")


def _encode_oauth_state(account_id: str, workspace_id: str) -> str:
    payload = {
        "account_id": account_id,
        "workspace_id": workspace_id,
        "expires_at": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
        "nonce": secrets.token_urlsafe(16),
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(_oauth_state_key(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def _decode_oauth_state(state: str) -> dict[str, Any] | None:
    try:
        raw, signature = state.rsplit(".", 1)
        expected = hmac.new(_oauth_state_key(), raw.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if int(payload.get("expires_at") or 0) < int(datetime.now(timezone.utc).timestamp()):
            return None
        if not payload.get("account_id") or not payload.get("workspace_id"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _financial_user_id_for_account(account_id: str) -> int:
    with get_connection() as conn:
        account = conn.execute(
            "SELECT primary_email,display_name FROM accounts WHERE id=%s",
            (account_id,),
        ).fetchone()
        if not account or not account.get("primary_email"):
            raise RuntimeError("La cuenta DINCR no tiene una identidad financiera válida.")
        existing = conn.execute(
            "SELECT id FROM users WHERE lower(email)=lower(%s) ORDER BY id LIMIT 1",
            (account["primary_email"],),
        ).fetchone()
        if existing:
            return int(existing["id"])
        created = conn.execute(
            """INSERT INTO users(email,name,country,timezone,created_at)
               VALUES(%s,%s,'Costa Rica','America/Costa_Rica',NOW()) RETURNING id""",
            (account["primary_email"], account.get("display_name") or "Usuario DINCR"),
        ).fetchone()
        conn.commit()
        return int(created["id"])


def _vault_create(conn, token: str, account_id: str, provider: str = "Gmail") -> str:
    row = conn.execute(
        "SELECT vault.create_secret(%s, NULL, %s) AS secret_id",
        (token, f"DINCR {provider} refresh token for account {account_id}"),
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
        rows = conn.execute(
            """SELECT id,google_email,status,granted_scopes,last_sync_at,last_success_at,
                      watch_expiration,last_error,connected_at,updated_at,
                      initial_scan_started_at,initial_scan_completed_at
               FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s
               ORDER BY connected_at,id""",
            (account_id, workspace_id),
        ).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) AS total FROM finva_email_candidates WHERE workspace_id=%s AND status='pending'",
            (workspace_id,),
        ).fetchone()
    connections = [{**dict(row), "provider": (
        "microsoft" if "Mail.Read" in (row.get("granted_scopes") or []) else "gmail"
    )} for row in rows]
    active = [row for row in connections if row["status"] == "active"]
    data = active[0] if active else connections[0] if connections else {}
    return {
        "status": "disconnected",
        "connected": bool(active),
        "needs_reauthorization": any(row["status"] == "reauthorization_required" for row in connections),
        "automatic_updates": any(row.get("watch_expiration") for row in active),
        "pending": int((pending or {}).get("total") or 0),
        **data,
        "connections": [{**row, "automatic_updates": bool(row.get("watch_expiration"))} for row in connections],
        "microsoft_available": all(os.getenv(name, "").strip() for name in (
            "DINCR_MICROSOFT_CLIENT_ID", "DINCR_MICROSOFT_CLIENT_SECRET", "DINCR_MICROSOFT_REDIRECT_URI",
        )),
        "consent": gmail_consent_status(),
        "retention": retention_policy(),
    }


def list_gmail_emails(status: str | None = None) -> dict[str, Any]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    allowed = {"pending", "auto_saved", "confirmed", "rejected", "duplicate"}
    if status and status not in allowed:
        raise HTTPException(status_code=422, detail="Estado de revisión inválido.")
    params: list[Any] = [account_id, workspace_id]
    status_filter = ""
    if status:
        status_filter = " AND c.status=%s"
        params.append(status)
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT m.id AS email_id,m.sender,m.subject,m.received_at,m.bank,m.status AS email_status,
                       m.parse_reason,c.id AS candidate_id,c.transaction_id,c.transaction_date,
                       c.description,c.amount,c.currency,c.transaction_type,c.movement_direction,
                       c.movement_kind,c.category,c.bank,c.source_account_label,
                       c.source_account_reference,c.destination_account_reference,c.counterparty,
                       c.parser_name,c.parser_version,c.extraction_method,c.confidence,
                       c.uncertainty_reason,c.status AS review_status,c.reviewed_at,c.created_at,
                       c.source_type,c.source_provider,c.statement_document_id,
                       c.is_internal_transfer,c.related_candidate_id,c.resolution_reason
                FROM finva_email_messages m
                LEFT JOIN finva_email_candidates c ON c.email_message_id=m.id
                WHERE m.account_id=%s AND m.workspace_id=%s{status_filter}
                ORDER BY COALESCE(m.received_at,m.created_at) DESC,m.id DESC
                LIMIT 200""",
            tuple(params),
        ).fetchall()
    return {"status": "ok", "items": [dict(row) for row in rows]}


def _create_candidate_transaction(conn, candidate: dict[str, Any], values: dict[str, Any]) -> int:
    category = normalize_category(values["category"], values["transaction_type"])
    source = "finva_statement" if candidate.get("source_type") == "statement" else "finva_gmail"
    note = (
        "Confirmado por el usuario desde un estado de cuenta."
        if candidate.get("source_type") == "statement"
        else "Confirmado por el usuario desde un correo bancario."
    )
    row = conn.execute(
        """INSERT INTO transactions(
               transaction_date,description,amount,transaction_type,category,account,source,notes,
               user_id,workspace_id,financial_account_id,created_at
           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) RETURNING id""",
        (
            values["transaction_date"], values["description"].strip(), values["amount"],
            values["transaction_type"], category, candidate.get("bank") or "",
            source, note,
            int(candidate["legacy_user_id"]), candidate["workspace_id"],
            candidate.get("financial_account_id"),
        ),
    ).fetchone()
    return int(row["id"])


def _publish_confirmed_financial_input(
    conn, candidate: dict[str, Any], values: dict[str, Any], transaction_id: int,
) -> None:
    """Publish the privacy-safe Phase 1 boundary in the same DB transaction.

    Downstream phases consume this canonical event instead of Gmail bodies,
    attachment text or parser evidence. Both inserts are idempotent so a retry
    cannot duplicate either the event or the user notification.
    """
    category = normalize_category(values["category"], values["transaction_type"])
    payload = {
        "transaction_id": transaction_id,
        "transaction_date": str(values["transaction_date"]),
        "amount": float(values["amount"]),
        "currency": str(candidate.get("currency") or "CRC"),
        "transaction_type": str(values["transaction_type"]),
        "category": category,
        "financial_account_id": candidate.get("financial_account_id"),
        "source": "statement" if candidate.get("source_type") == "statement" else "gmail",
    }
    conn.execute(
        """INSERT INTO financial_input_events(
               account_id,workspace_id,user_id,event_name,contract_version,
               transaction_id,payload,created_at
           ) VALUES(%s,%s,%s,'transaction_confirmed','financial-input-v1',%s,%s::jsonb,NOW())
           ON CONFLICT(transaction_id,event_name,contract_version) DO NOTHING""",
        (
            candidate["account_id"], candidate["workspace_id"], int(candidate["legacy_user_id"]),
            transaction_id, json.dumps(payload, default=str),
        ),
    )
    conn.execute(
        """INSERT INTO notification_jobs(
               user_id,workspace_id,title,body,category,scheduled_at,
               reference_type,reference_id,dedupe_key,payload
           ) VALUES(%s,%s,%s,%s,'financial_import',NOW(),
                    'transaction',%s,%s,%s::jsonb)
           ON CONFLICT DO NOTHING""",
        (
            int(candidate["legacy_user_id"]), candidate["workspace_id"],
            "Movimiento confirmado",
            f"DINCR guardó {values['description'].strip()} por {float(values['amount']):,.2f} {payload['currency']}.",
            str(transaction_id), f"financial-input-v1:{transaction_id}",
            json.dumps({"event": "transaction_confirmed", "transaction_id": transaction_id}),
        ),
    )


def review_gmail_candidate(candidate_id: int, action: str, corrections: dict[str, Any] | None = None) -> dict[str, Any]:
    if action not in {"accept", "reject"}:
        raise HTTPException(status_code=422, detail="Acción de revisión inválida.")
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        candidate = conn.execute(
            """SELECT c.*,g.legacy_user_id
               FROM finva_email_candidates c
               JOIN finva_email_messages m ON m.id=c.email_message_id
               JOIN finva_gmail_connections g ON g.id=m.connection_id
               WHERE c.id=%s AND c.account_id=%s AND c.workspace_id=%s
               FOR UPDATE""",
            (candidate_id, account_id, workspace_id),
        ).fetchone()
        if not candidate:
            raise HTTPException(status_code=404, detail="Correo financiero no encontrado.")
        candidate = dict(candidate)
        if candidate["status"] != "pending":
            return {"status": candidate["status"], "candidate_id": candidate_id, "transaction_id": candidate.get("transaction_id")}
        if action == "reject":
            conn.execute(
                """UPDATE finva_email_candidates
                   SET status='rejected',reviewed_at=NOW(),corrected_fields=ARRAY[]::TEXT[],updated_at=NOW()
                   WHERE id=%s""",
                (candidate_id,),
            )
            conn.execute("UPDATE finva_email_messages SET status='rejected' WHERE id=%s", (candidate["email_message_id"],))
            if candidate.get("resolution_reason") == "paired_owned_transfer" and candidate.get("related_candidate_id"):
                resolve_candidate(conn, int(candidate["related_candidate_id"]))
            conn.commit()
            return {"status": "rejected", "candidate_id": candidate_id, "transaction_id": None}

        if candidate.get("is_internal_transfer"):
            conn.execute(
                """UPDATE finva_email_candidates
                   SET status='confirmed',reviewed_at=NOW(),corrected_fields=ARRAY[]::TEXT[],updated_at=NOW()
                   WHERE id=%s""",
                (candidate_id,),
            )
            conn.execute("UPDATE finva_email_messages SET status='confirmed' WHERE id=%s", (candidate["email_message_id"],))
            if candidate.get("resolution_reason") == "paired_owned_transfer" and candidate.get("related_candidate_id"):
                conn.execute(
                    """UPDATE finva_email_candidates SET status='confirmed',reviewed_at=NOW(),updated_at=NOW()
                       WHERE id=%s AND account_id=%s AND workspace_id=%s
                         AND status='pending' AND is_internal_transfer=TRUE AND transaction_id IS NULL""",
                    (candidate["related_candidate_id"], account_id, workspace_id),
                )
                conn.execute(
                    """UPDATE finva_email_messages SET status='confirmed'
                       WHERE id IN (SELECT email_message_id FROM finva_email_candidates
                                    WHERE id=%s AND account_id=%s AND workspace_id=%s
                                      AND status='confirmed' AND is_internal_transfer=TRUE)""",
                    (candidate["related_candidate_id"], account_id, workspace_id),
                )
            conn.commit()
            return {"status": "confirmed", "candidate_id": candidate_id, "transaction_id": None, "is_internal_transfer": True}

        values = {
            "transaction_date": candidate["transaction_date"],
            "description": candidate["description"],
            "amount": candidate["amount"],
            "transaction_type": candidate["transaction_type"],
            "category": candidate["category"],
        }
        if corrections:
            values.update(corrections)
        corrected_fields = sorted(
            key for key, value in (corrections or {}).items()
            if value != candidate.get(key)
        )
        transaction_id = _create_candidate_transaction(conn, candidate, values)
        _publish_confirmed_financial_input(conn, candidate, values, transaction_id)
        category = normalize_category(values["category"], values["transaction_type"])
        conn.execute(
            """UPDATE finva_email_candidates
               SET transaction_id=%s,transaction_date=%s,description=%s,amount=%s,
                   transaction_type=%s,category=%s,status='confirmed',reviewed_at=NOW(),
                   corrected_fields=%s,updated_at=NOW()
               WHERE id=%s""",
            (transaction_id, values["transaction_date"], values["description"].strip(), values["amount"],
             values["transaction_type"], category, corrected_fields, candidate_id),
        )
        conn.execute("UPDATE finva_email_messages SET status='confirmed' WHERE id=%s", (candidate["email_message_id"],))
        conn.commit()
    return {"status": "confirmed", "candidate_id": candidate_id, "transaction_id": transaction_id}


def begin_gmail_connection() -> dict[str, str]:
    require_gmail_consent()
    client_id, _, redirect_uri = _google_config()
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    state = _encode_oauth_state(account_id, workspace_id)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent select_account",
        "state": state,
    }
    return {"authorization_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}


def finish_gmail_connection(code: str | None, state: str | None, error: str | None = None):
    if error or not code or not state:
        return RedirectResponse(_return_url("denied"), status_code=302)

    oauth_state = _decode_oauth_state(state)
    if not oauth_state:
        return RedirectResponse(_return_url("invalid_state"), status_code=302)

    account_id = str(oauth_state["account_id"])
    workspace_id = str(oauth_state["workspace_id"])
    with get_connection() as conn:
        if not _has_active_vip_access(conn, account_id):
            return RedirectResponse(_return_url("vip_required"), status_code=302)

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

    try:
        legacy_user_id = _financial_user_id_for_account(account_id)
    except Exception:
        return RedirectResponse(_return_url("identity_failed"), status_code=302)
    with get_connection() as conn:
        # Recheck after the external OAuth exchange so a concurrent downgrade
        # cannot persist credentials for an account that is no longer VIP.
        if not _has_active_vip_access(conn, account_id):
            return RedirectResponse(_return_url("vip_required"), status_code=302)
        current = conn.execute(
            """SELECT id,refresh_token_secret_id,granted_scopes FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s AND lower(google_email)=%s FOR UPDATE""",
            (account_id, workspace_id, google_email),
        ).fetchone()
        if current and "Mail.Read" in (current.get("granted_scopes") or []):
            return RedirectResponse(_return_url("already_connected_elsewhere"), status_code=302)
        secret_id = _vault_create(conn, refresh_token, account_id)
        if current:
            row = conn.execute(
                """UPDATE finva_gmail_connections SET
                   legacy_user_id=%s,refresh_token_secret_id=%s::uuid,granted_scopes=%s,
                   status='active',last_error=NULL,history_id=NULL,watch_expiration=NULL,
                   connected_at=NOW(),updated_at=NOW() WHERE id=%s RETURNING id""",
                (legacy_user_id, secret_id, [GMAIL_SCOPE], current["id"]),
            ).fetchone()
        else:
            row = conn.execute(
                """INSERT INTO finva_gmail_connections(
                   account_id,workspace_id,legacy_user_id,google_email,refresh_token_secret_id,
                   granted_scopes,status,connected_at,updated_at
               ) VALUES(%s,%s,%s,%s,%s::uuid,%s,'active',NOW(),NOW())
               RETURNING id""",
                (account_id, workspace_id, legacy_user_id, google_email, secret_id, [GMAIL_SCOPE]),
            ).fetchone()
        old_secret = (current or {}).get("refresh_token_secret_id")
        if old_secret and str(old_secret) != secret_id:
            _vault_delete(conn, str(old_secret))
        conn.commit()

    _start_watch(int(row["id"]), service, suppress_errors=True)
    try:
        _sync_connection(int(row["id"]), service=service, max_results=100)
    except Exception:
        pass
    return RedirectResponse(_return_url("connected"), status_code=302)


def disconnect_gmail(connection_id: int | None = None) -> dict[str, str]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,refresh_token_secret_id,status,granted_scopes FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s AND (%s::bigint IS NULL OR id=%s)
               AND status<>'disabled' FOR UPDATE""",
            (account_id, workspace_id, connection_id, connection_id),
        ).fetchall()
        if connection_id is None and len(rows) > 1:
            raise HTTPException(status_code=422, detail="Elegí cuál correo querés desconectar.")
        row = rows[0] if rows else None
        if not row:
            return {"status": "disconnected"}
        if GMAIL_SCOPE in (row.get("granted_scopes") or []):
            try:
                token = _vault_read(conn, str(row["refresh_token_secret_id"]))
                requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10)
            except Exception:
                pass
        conn.execute(
            """UPDATE finva_gmail_connections
               SET status='disabled',history_id=NULL,watch_expiration=NULL,last_error=NULL,
                   initial_scan_page_token=NULL,updated_at=NOW()
               WHERE id=%s""",
            (int(row["id"]),),
        )
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


def _insert_dincr_candidate(
    conn, *, email_message_id: int, connection: dict[str, Any],
    candidate: dict[str, Any], statement_document_id: int | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        """INSERT INTO finva_email_candidates(
               email_message_id,account_id,workspace_id,transaction_id,statement_document_id,
               movement_index,source_type,source_provider,source_record_key,institution_country,
               transaction_date,transaction_time,description,amount,currency,original_amount,
               original_currency,transaction_type,movement_direction,movement_kind,category,bank,
               source_account_label,source_account_reference,destination_account_reference,
               counterparty,external_reference,parser_name,parser_version,extraction_method,
               confidence,uncertainty_reason,dedupe_key,is_internal_transfer,status,raw_payload
           ) VALUES(
               %s,%s,%s,NULL,%s,
               %s,%s,%s,%s,%s,
               %s,%s,%s,%s,%s,%s,
               %s,%s,%s,%s,%s,%s,
               %s,%s,%s,
               %s,%s,%s,%s,%s,
               %s,%s,%s,%s,'pending',%s::jsonb
           ) RETURNING id""",
        (
            email_message_id, connection["account_id"], connection["workspace_id"],
            statement_document_id, candidate["movement_index"], candidate["source_type"],
            candidate["source_provider"], candidate["source_record_key"],
            candidate["institution_country"], candidate["transaction_date"],
            candidate["transaction_time"], candidate["description"], candidate["amount"],
            candidate["currency"], candidate["original_amount"], candidate["original_currency"],
            candidate["transaction_type"], candidate["movement_direction"],
            candidate["movement_kind"], candidate["category"], candidate["bank"],
            candidate["source_account_label"], candidate["source_account_reference"],
            candidate["destination_account_reference"], candidate["counterparty"],
            candidate["external_reference"], candidate["parser_name"], candidate["parser_version"],
            candidate["extraction_method"], candidate["confidence"], candidate["uncertainty_reason"],
            candidate["dedupe_key"], candidate["is_internal_transfer"],
            json.dumps(candidate["raw_payload"], default=str),
        ),
    ).fetchone()
    candidate_id = int(row["id"])
    discover_candidate_account(
        conn, candidate_id=candidate_id, candidate=candidate,
        account_id=str(connection["account_id"]), workspace_id=str(connection["workspace_id"]),
        legacy_user_id=int(connection["legacy_user_id"]),
    )
    link_received_payroll(
        conn, candidate_id=candidate_id, candidate=candidate,
        workspace_id=str(connection["workspace_id"]),
    )
    return resolve_candidate(conn, candidate_id)


def _process_message(service, connection: dict[str, Any], message_id: str) -> str:
    full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {item.get("name", "").lower(): item.get("value", "") for item in full.get("payload", {}).get("headers", [])}
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    payload = full.get("payload") or {}
    body = _plain_text(payload) or full.get("snippet", "")
    attachments = collect_attachments(payload)
    attachment_text, attachment_names = extract_pdf_attachment_text(service, message_id, attachments)
    received_at = None
    if headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc).isoformat()
        except Exception:
            received_at = None

    return _ingest_message(
        connection, message_id, subject=subject, sender=sender, body=body,
        attachment_text=attachment_text, attachment_names=attachment_names,
        received_at=received_at,
    )


def _ingest_message(
    connection: dict[str, Any], message_id: str, *, subject: str, sender: str,
    body: str, attachment_text: str = "", attachment_names: list[str] | None = None,
    received_at: str | None = None,
) -> str:
    """Shared candidate pipeline for mail providers; no raw message persists."""
    attachment_names = attachment_names or []

    display_name = str(connection.get("display_name") or "")
    payroll_report = parse_ccss_order_patronal(subject, sender, attachment_text or body)
    financial_text = "\n".join(item for item in (body, attachment_text) if item)
    parsed = {} if payroll_report else (
        parse_popular_email_document(
            subject=_adapt_identity(subject, display_name),
            sender=sender,
            body=_adapt_identity(financial_text, display_name),
            attachment_text=_adapt_identity(attachment_text, display_name),
            received_at=received_at,
        ) or parse_financial_email(
            _adapt_identity(subject, display_name), sender,
            _adapt_identity(financial_text, display_name), received_at,
        )
    )
    if parsed and not payroll_report:
        parsed = identify_received_payroll(parsed, subject=subject, body=financial_text)
    kind = "payroll_statement" if payroll_report else str(parsed.get("email_kind") or "ignored")
    if kind == "ignored" and parsed.get("transaction_type") == "internal_transfer" and parsed.get("amount"):
        # Legacy parser ownership hints become reviewable evidence, never the
        # final decision. Confirmed Financial Identity resolves ownership.
        parsed = {**parsed, "transaction_type": "transfer", "category": "Transferencia"}
        kind = "movement"
    confidence = 1.0 if payroll_report else float(parsed.get("confidence") or 0)
    status = "ignored"
    transaction_id = None

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id,status FROM finva_email_messages WHERE connection_id=%s AND provider_message_id=%s",
            (int(connection["id"]), message_id),
        ).fetchone()
        if existing:
            statement_exists = kind == "statement" and conn.execute(
                "SELECT 1 FROM finva_statement_documents WHERE email_message_id=%s",
                (int(existing["id"]),),
            ).fetchone()
            if kind != "statement" or statement_exists:
                return "duplicate"
            email_row = existing
            conn.execute(
                """UPDATE finva_email_messages
                   SET bank=%s,status='statement',parse_reason=%s WHERE id=%s""",
                (
                    parsed.get("bank") or "unknown",
                    parsed.get("confidence_reason") or "Estado de cuenta listo para procesar.",
                    int(existing["id"]),
                ),
            )
        else:
            email_row = conn.execute(
                """INSERT INTO finva_email_messages(
                       connection_id,account_id,workspace_id,provider_message_id,sender,subject,received_at,
                       bank,status,parse_reason
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    int(connection["id"]), connection["account_id"], connection["workspace_id"], message_id,
                    sender[:500], subject[:500], received_at,
                    "ccss" if payroll_report else parsed.get("bank") or "unknown", kind,
                    (f"Orden patronal CCSS {payroll_report['period_month']} procesada."
                     if payroll_report else parsed.get("confidence_reason") or parsed.get("ignore_reason") or ""),
                ),
            ).fetchone()

        if payroll_report:
            conn.execute(
                """INSERT INTO payroll_salary_reports(
                       user_id,workspace_id,email_message_id,provider_message_id,period_month,
                       reported_salary,trans_previous_salary,previous_salary,daily_subsidy,
                       employer_number,verification_code,source,updated_at
                   ) VALUES(%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,'ccss_order_patronal',NOW())
                   ON CONFLICT(workspace_id,period_month) DO UPDATE SET
                       provider_message_id=EXCLUDED.provider_message_id,
                       reported_salary=EXCLUDED.reported_salary,
                       trans_previous_salary=EXCLUDED.trans_previous_salary,
                       previous_salary=EXCLUDED.previous_salary,
                       daily_subsidy=EXCLUDED.daily_subsidy,
                       employer_number=EXCLUDED.employer_number,
                       verification_code=EXCLUDED.verification_code,
                       source=EXCLUDED.source,updated_at=NOW()""",
                (
                    int(connection["legacy_user_id"]), connection["workspace_id"], message_id,
                    payroll_report["period_month"], payroll_report["reported_salary"],
                    payroll_report["trans_previous_salary"], payroll_report["previous_salary"],
                    payroll_report["daily_subsidy"], payroll_report.get("employer_number"),
                    payroll_report.get("verification_code"),
                ),
            )
            status = "payroll_statement"
        elif kind == "statement":
            document_text = attachment_text or financial_text
            document_hash = statement_hash(document_text)
            movements = parse_statement_movements(str(parsed.get("bank") or "unknown"), document_text)
            document_status = (
                "candidates_ready" if movements else
                "unsupported" if parsed.get("bank") not in {"bac", "multimoney", "popular"} else "empty"
            )
            document_row = conn.execute(
                """INSERT INTO finva_statement_documents(
                       email_message_id,account_id,workspace_id,bank,statement_month,
                       attachment_names,document_hash,parser_name,parser_version,movements_found,status
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    int(email_row["id"]), connection["account_id"], connection["workspace_id"],
                    parsed.get("bank") or "unknown", parsed.get("statement_month"),
                    attachment_names, document_hash, STATEMENT_PARSER_NAME,
                    STATEMENT_PARSER_VERSION, len(movements), document_status,
                ),
            ).fetchone()
            resolutions = []
            for index, movement in enumerate(movements):
                candidate = statement_candidate(
                    movement, bank=str(parsed.get("bank") or "unknown"),
                    document_hash=document_hash, movement_index=index,
                    statement_text=document_text,
                )
                resolutions.append(_insert_dincr_candidate(
                    conn, email_message_id=int(email_row["id"]), connection=connection,
                    candidate=candidate, statement_document_id=int(document_row["id"]),
                ))
            if movements:
                status = "duplicate" if all(item.get("status") == "duplicate" for item in resolutions) else "pending"
                reason = f"Estado de cuenta procesado: {len(movements)} movimiento(s) listos para revisión."
            else:
                status = "ignored"
                reason = "Estado de cuenta detectado, pero el formato todavía no tiene filas firmadas compatibles."
            conn.execute("UPDATE finva_email_messages SET parse_reason=%s WHERE id=%s", (reason, int(email_row["id"])))
        elif kind == "movement" and parsed.get("amount") and parsed.get("transaction_type"):
            candidate = canonical_candidate(
                parsed,
                provider_message_id=message_id,
                subject=subject,
            )
            resolution = _insert_dincr_candidate(
                conn, email_message_id=int(email_row["id"]), connection=connection,
                candidate=candidate,
            )
            status = str(resolution.get("status") or "pending")
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
        if GMAIL_SCOPE not in (row.get("granted_scopes") or []):
            raise RuntimeError("Este correo no está conectado mediante Gmail.")
        if not _has_active_vip_access(conn, str(row["account_id"])):
            raise HTTPException(
                status_code=403,
                detail="La automatización de Gmail está disponible únicamente en el plan VIP.",
            )
        token = _vault_read(conn, str(row["refresh_token_secret_id"]))
    return dict(row), token


def _sync_connection(connection_id: int, service=None, max_results: int = 100) -> dict[str, Any]:
    connection, token = _connection_with_token(connection_id)
    try:
        service = service or _credentials(token)
        initial_sync = not connection.get("initial_scan_completed_at")
        next_initial_page = None
        if initial_sync:
            financial_messages, next_initial_page = _list_message_page(
                service, _year_to_date_query(),
                page_token=connection.get("initial_scan_page_token"), limit=50,
            )
        else:
            financial_messages = _list_message_refs(service, DINCR_QUERY, max_results)
        payroll_messages = _list_message_refs(service, _aguinaldo_gmail_query(), 100)
        messages = {
            item["id"]: item
            for item in [*financial_messages, *payroll_messages]
            if item.get("id")
        }
        results = [_process_message(service, connection, item["id"]) for item in messages.values()]
    except Exception as exc:
        message = str(exc).lower()
        if "invalid_grant" in message or "token has been expired" in message or "revoked" in message:
            _mark_reconnect(connection_id)
            raise HTTPException(status_code=409, detail="La conexión de Gmail venció. Volvé a autorizarla desde DINCR.") from exc
        with get_connection() as conn:
            conn.execute(
                "UPDATE finva_gmail_connections SET last_sync_at=NOW(),last_error=%s,updated_at=NOW() WHERE id=%s",
                ("No se pudo completar la sincronización.", connection_id),
            )
            conn.commit()
        raise

    with get_connection() as conn:
        conn.execute(
            """UPDATE finva_gmail_connections
               SET status='active',last_sync_at=NOW(),last_success_at=NOW(),last_error=NULL,
                   initial_scan_started_at=CASE WHEN %s THEN COALESCE(initial_scan_started_at,NOW()) ELSE initial_scan_started_at END,
                   initial_scan_page_token=CASE WHEN %s THEN %s ELSE initial_scan_page_token END,
                   initial_scan_completed_at=CASE WHEN %s AND %s IS NULL THEN NOW() ELSE initial_scan_completed_at END,
                   updated_at=NOW()
               WHERE id=%s""",
            (initial_sync, initial_sync, next_initial_page, initial_sync, next_initial_page, connection_id),
        )
        conn.commit()
    return {
        "status": "ok",
        "scan_scope": "year_to_date" if initial_sync else "recent",
        "initial_scan_complete": (not initial_sync) or next_initial_page is None,
        "found": len(results),
        "auto_saved": results.count("auto_saved"),
        "pending": results.count("pending"),
        "payroll_reports": results.count("payroll_statement"),
        "duplicates": results.count("duplicate"),
    }


def sync_current_gmail() -> dict[str, Any]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,granted_scopes FROM finva_gmail_connections
               WHERE account_id=%s AND workspace_id=%s AND status='active' ORDER BY id""",
            (account_id, workspace_id),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Primero conectá Gmail.")
    results = []
    errors = []
    for row in rows:
        try:
            if "Mail.Read" in (row.get("granted_scopes") or []):
                from backend.user_product.microsoft_mail import sync_connection
                results.append(sync_connection(int(row["id"])))
            else:
                results.append(_sync_connection(int(row["id"])))
        except Exception:
            errors.append(int(row["id"]))
    if not results:
        raise HTTPException(status_code=409, detail="No se pudo actualizar ningún correo. Revisá tus conexiones.")
    # Also reconcile notifications received before the user connected the
    # second inbox or confirmed the ownership of both financial accounts.
    with get_connection() as conn:
        reevaluate_workspace_candidates(conn, account_id=account_id, workspace_id=workspace_id)
        conn.commit()
    return {
        "status": "partial" if errors else "ok", "connections": len(rows), "failed_connections": errors,
        "scan_scope": "year_to_date" if any(r["scan_scope"] == "year_to_date" for r in results) else "recent",
        "initial_scan_complete": all(r["initial_scan_complete"] for r in results),
        **{key: sum(r.get(key, 0) for r in results) for key in ("found", "auto_saved", "pending", "payroll_reports", "duplicates")},
    }


def _start_watch(connection_id: int, service, suppress_errors: bool = False) -> None:
    topic = os.getenv("DINCR_GMAIL_PUBSUB_TOPIC", "").strip()
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
    expected = os.getenv("DINCR_GMAIL_CRON_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="DINCR_GMAIL_CRON_SECRET no está configurado.")
    if not secret or not secrets.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="Secreto de mantenimiento inválido.")
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT c.id,c.granted_scopes
               FROM finva_gmail_connections c
               JOIN account_subscriptions s ON s.account_id=c.account_id
               JOIN plans p ON p.id=s.plan_id
               WHERE c.status='active'
                 AND s.status='active'
                 AND p.code='vip'
                 AND (
                   s.access_source<>'courtesy'
                   OR (s.expires_at IS NOT NULL AND s.expires_at>NOW())
                 )
               ORDER BY c.id"""
        ).fetchall()
    completed = 0
    reconnect = 0
    for row in rows:
        connection_id = int(row["id"])
        try:
            if "Mail.Read" in (row.get("granted_scopes") or []):
                from backend.user_product.microsoft_mail import sync_connection
                sync_connection(connection_id)
            else:
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
    retention = apply_gmail_retention()
    return {"status": "ok", "connections": len(rows), "completed": completed, "reconnect": reconnect, "retention": retention}


def process_gmail_push(payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    expected = os.getenv("DINCR_GMAIL_PUBSUB_VERIFICATION_TOKEN", "")
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
        rows = conn.execute(
            """SELECT c.id
               FROM finva_gmail_connections c
               JOIN account_subscriptions s ON s.account_id=c.account_id
               JOIN plans p ON p.id=s.plan_id
               WHERE c.google_email=%s AND %s=ANY(c.granted_scopes)
                 AND c.status='active'
                 AND s.status='active'
                 AND p.code='vip'
                 AND (
                   s.access_source<>'courtesy'
                   OR (s.expires_at IS NOT NULL AND s.expires_at>NOW())
                 )""",
            (email, GMAIL_SCOPE),
        ).fetchall()
    if not rows:
        return {"status": "ignored"}
    completed = 0
    for row in rows:
        try:
            _sync_connection(int(row["id"]), max_results=50)
            completed += 1
        except Exception:
            continue
    return {"status": "ok" if completed == len(rows) else "partial", "connections": len(rows), "completed": completed}
