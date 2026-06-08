from __future__ import annotations

import base64
import html
import os
import re
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from fastapi import HTTPException, status

from backend.auth.current_user import get_current_user, get_current_user_id, require_roles
from backend.core.database import get_connection
from backend.finance.category_catalog import normalize_category
from backend.email_monitor.parser import (
    fingerprint_candidate,
    fingerprint_email,
    parse_financial_email,
)

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "gatotico99@gmail.com")
CRON_SECRET = os.getenv("EMAIL_MONITOR_CRON_SECRET", "")
DEFAULT_QUERY = os.getenv(
    "GMAIL_FINANCE_QUERY",
    '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular OR from:popular OR "BAC - SINPE" OR "Banco Popular") ("Notificación de transacción" OR "Notificación de Transferencia" OR "Transacción realizada" OR "Estado de cuenta" OR "Estado de Cuenta" OR "estados de cuenta" OR SINPE OR transferencia OR compra OR pago OR depósito OR deposito OR retiro OR abono)',
)
# Fase 6.2: no se guarda nada automático. Primero validamos lectura limpia.
AUTO_COMMIT_CONFIDENCE = float(os.getenv("EMAIL_AUTO_COMMIT_CONFIDENCE", "999"))


def build_current_month_gmail_query(base_query: str | None = None, today: date | None = None) -> str:
    """Return a Gmail query scoped to the current calendar month.

    Gmail search uses after:/before: dates in YYYY/MM/DD. `before` is exclusive,
    so we use first day of next month.
    """
    today = today or date.today()
    start = today.replace(day=1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)

    base = (base_query or DEFAULT_QUERY or '').strip()

    # Remove broad recency filters so the month range is the source of truth.
    base = re.sub(r"\bnewer_than:\S+", "", base).strip()
    base = re.sub(r"\bafter:\d{4}/\d{1,2}/\d{1,2}", "", base).strip()
    base = re.sub(r"\bbefore:\d{4}/\d{1,2}/\d{1,2}", "", base).strip()

    return f"{base} after:{start:%Y/%m/%d} before:{end:%Y/%m/%d}".strip()


def ensure_email_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_monitor_settings (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            auto_commit_confidence NUMERIC NOT NULL DEFAULT 0.90,
            monitored_senders TEXT[] NOT NULL DEFAULT ARRAY['bac','credomatic','popular','multimoney'],
            gmail_query TEXT NOT NULL DEFAULT '',
            last_scan_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_ingested_messages (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'gmail',
            provider_message_id TEXT,
            fingerprint TEXT NOT NULL,
            sender TEXT,
            subject TEXT,
            received_at TIMESTAMPTZ,
            bank TEXT,
            status TEXT NOT NULL DEFAULT 'processed',
            raw_excerpt TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, fingerprint),
            UNIQUE(user_id, provider, provider_message_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_transaction_candidates (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
            fingerprint TEXT NOT NULL,
            transaction_id BIGINT,
            transaction_date DATE NOT NULL,
            description TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            transaction_type TEXT NOT NULL,
            category TEXT NOT NULL,
            account TEXT DEFAULT '',
            source TEXT NOT NULL DEFAULT 'email_monitor',
            notes TEXT DEFAULT '',
            original_amount NUMERIC,
            original_currency TEXT,
            exchange_rate NUMERIC,
            confidence NUMERIC NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            review_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, fingerprint)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_statement_documents (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
            bank TEXT NOT NULL,
            subject TEXT,
            statement_month TEXT,
            received_at TIMESTAMPTZ,
            attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            extracted_text_excerpt TEXT,
            status TEXT NOT NULL DEFAULT 'pending_reconciliation',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, email_message_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS card_aliases (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            card_last4 TEXT NOT NULL,
            owner_label TEXT NOT NULL,
            relationship TEXT,
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, card_last4)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_card_aliases_user
        ON card_aliases(user_id)
        """
    )


def _owner_user_id(conn) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM users
        WHERE email = 'gatotico99@gmail.com'
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])

    row = conn.execute(
        """
        SELECT id
        FROM users
        WHERE email = %s
        ORDER BY id
        LIMIT 1
        """,
        (OWNER_EMAIL,),
    ).fetchone()
    return int(row["id"]) if row else None


def _require_owner_user() -> dict[str, Any]:
    user = require_roles("owner")
    return user


def get_email_monitor_status() -> dict[str, Any]:
    user = _require_owner_user()
    user_id = int(user["id"])

    with get_connection() as conn:
        ensure_email_tables(conn)
        settings = conn.execute(
            """
            INSERT INTO email_monitor_settings (user_id, gmail_query)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO UPDATE SET updated_at = NOW()
            RETURNING *
            """,
            (user_id, DEFAULT_QUERY),
        ).fetchone()

        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_candidates,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                COUNT(*) FILTER (WHERE status = 'confirmed') AS confirmed,
                COUNT(*) FILTER (WHERE status = 'auto_saved') AS auto_saved,
                COUNT(*) FILTER (WHERE status = 'duplicate') AS duplicate,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected
            FROM email_transaction_candidates
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchone()
        ignored = conn.execute(
            """
            SELECT COUNT(*) AS ignored
            FROM email_ingested_messages
            WHERE user_id = %s AND status = 'ignored'
            """,
            (user_id,),
        ).fetchone()
        totals = dict(totals)
        totals["ignored"] = int((ignored or {}).get("ignored") or 0)
        conn.commit()

    gmail_ready = all(
        os.getenv(key)
        for key in ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"]
    )

    return {
        "status": "OK",
        "owner_only": True,
        "gmail_ready": gmail_ready,
        "settings": dict(settings),
        "totals": totals if isinstance(totals, dict) else dict(totals),
        "required_env": [
            "GMAIL_CLIENT_ID",
            "GMAIL_CLIENT_SECRET",
            "GMAIL_REFRESH_TOKEN",
        ],
        "optional_env": [
            "GMAIL_FINANCE_QUERY",
            "EMAIL_AUTO_COMMIT_CONFIDENCE",
            "EMAIL_MONITOR_CRON_SECRET",
        ],
    }


def _insert_transaction(conn, user_id: int, candidate: dict[str, Any]) -> int:
    if candidate.get("transaction_type") in {"statement", "ignored"}:
        raise ValueError("Los estados de cuenta o correos ignorados no se guardan como transacciones directas.")
    category = normalize_category(candidate["category"], candidate["transaction_type"])
    row = conn.execute(
        """
        INSERT INTO transactions (
            user_id,
            transaction_date,
            description,
            amount,
            transaction_type,
            category,
            account,
            source,
            notes,
            original_amount,
            original_currency,
            exchange_rate,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (
            user_id,
            candidate["transaction_date"],
            candidate["description"],
            candidate["amount"],
            candidate["transaction_type"],
            category,
            candidate.get("account", ""),
            candidate.get("source", "email_monitor"),
            candidate.get("notes", ""),
            candidate.get("original_amount"),
            candidate.get("original_currency"),
            candidate.get("exchange_rate"),
        ),
    ).fetchone()
    return int(row["id"])


def _extract_card_last4_from_account(account: str | None) -> str | None:
    match = re.search(r"(\d{4})", account or "")
    return match.group(1) if match else None


def _enrich_candidate_with_card_alias(conn, user_id: int, candidate: dict[str, Any]) -> dict[str, Any]:
    """Attach owner labels such as Kenneth/Emily/Sidey for additional cards.

    This is only metadata in notes/category review; it never changes money values.
    """
    last4 = _extract_card_last4_from_account(candidate.get("account"))
    if not last4:
        return candidate
    row = conn.execute(
        """
        SELECT owner_label, relationship, is_primary
        FROM card_aliases
        WHERE user_id = %s AND card_last4 = %s
        LIMIT 1
        """,
        (user_id, last4),
    ).fetchone()
    if not row:
        return candidate
    owner_label = row["owner_label"]
    relationship = row.get("relationship") if hasattr(row, "get") else row["relationship"]
    primary = bool(row["is_primary"])
    notes = candidate.get("notes") or ""
    extra = f"titular tarjeta: {owner_label}"
    if relationship:
        extra += f" ({relationship})"
    if primary:
        extra += " | tarjeta principal"
    if extra not in notes:
        candidate["notes"] = f"{notes} | {extra}" if notes else extra
    return candidate


def _transaction_duplicate_exists(conn, user_id: int, candidate: dict[str, Any]) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM transactions
        WHERE user_id = %s
        AND transaction_date = %s
        AND ABS(amount - %s) < 0.01
        AND transaction_type = %s
        AND LOWER(description) = LOWER(%s)
        LIMIT 1
        """,
        (
            user_id,
            candidate["transaction_date"],
            candidate["amount"],
            candidate["transaction_type"],
            candidate["description"],
        ),
    ).fetchone()
    return bool(row)


def scan_email_text(
    *,
    subject: str,
    sender: str,
    body: str,
    received_at: str | None = None,
    auto_commit: bool = False,
    user_id: int | None = None,
    provider_message_id: str | None = None,
    attachment_names: list[str] | None = None,
) -> dict[str, Any]:
    if user_id is None:
        _require_owner_user()
        user_id = get_current_user_id()

    parsed = parse_financial_email(subject, sender, body, received_at)
    parsed["attachment_names"] = attachment_names or []
    email_fp = fingerprint_email(sender, subject, body, received_at)

    # Correos informativos, login, publicidad y seguros no generan candidatos.
    # Se guardan como ingested/ignored para evitar reprocesarlos y para auditoría.
    if parsed.get("email_kind") == "ignored":
        with get_connection() as conn:
            ensure_email_tables(conn)
            existing_msg = conn.execute(
                """
                SELECT id
                FROM email_ingested_messages
                WHERE user_id = %s
                AND fingerprint = %s
                """,
                (user_id, email_fp),
            ).fetchone()

            if existing_msg:
                conn.commit()
                return {
                    "status": "DUPLICATE_IGNORED_EMAIL",
                    "message": "Correo ignorado ya procesado.",
                    "ignored": True,
                    "reason": parsed.get("ignore_reason") or parsed.get("confidence_reason"),
                }

            conn.execute(
                """
                INSERT INTO email_ingested_messages (
                    user_id, provider, provider_message_id, fingerprint, sender, subject,
                    received_at, bank, status, raw_excerpt
                )
                VALUES (%s, 'gmail', %s, %s, %s, %s, %s, %s, 'ignored', %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    user_id,
                    provider_message_id,
                    email_fp,
                    sender,
                    subject,
                    received_at,
                    parsed["bank"],
                    (parsed.get("ignore_reason") or body)[:1200],
                ),
            )
            conn.commit()

        return {
            "status": "IGNORED_EMAIL",
            "message": parsed.get("ignore_reason") or "Correo ignorado.",
            "ignored": True,
            "candidate": None,
        }

    candidate_fp = fingerprint_candidate(
        user_id=user_id,
        transaction_date=parsed["transaction_date"],
        amount=float(parsed["amount"]),
        transaction_type=parsed["transaction_type"],
        description=parsed["description"],
        bank=parsed["bank"],
    )

    with get_connection() as conn:
        ensure_email_tables(conn)

        existing_msg = conn.execute(
            """
            SELECT id
            FROM email_ingested_messages
            WHERE user_id = %s
            AND fingerprint = %s
            """,
            (user_id, email_fp),
        ).fetchone()

        if existing_msg:
            existing_candidate = conn.execute(
                """
                SELECT *
                FROM email_transaction_candidates
                WHERE user_id = %s
                AND fingerprint = %s
                """,
                (user_id, candidate_fp),
            ).fetchone()
            if existing_candidate:
                conn.commit()
                return {
                    "status": "DUPLICATE_EMAIL",
                    "message": "Correo ya procesado.",
                    "candidate": dict(existing_candidate),
                }

            # Parser upgraded: a message previously marked ignored may now parse correctly.
            # Reuse the existing ingested email row and create the missing candidate.
            email_message_id = int(existing_msg["id"])
            conn.execute(
                """
                UPDATE email_ingested_messages
                SET status = 'processed', bank = %s, subject = %s, sender = %s,
                    received_at = COALESCE(%s, received_at), raw_excerpt = %s
                WHERE id = %s AND user_id = %s
                """,
                (parsed["bank"], subject, sender, received_at, body[:1200], email_message_id, user_id),
            )
        else:
            email_row = conn.execute(
                """
                INSERT INTO email_ingested_messages (
                    user_id, provider, provider_message_id, fingerprint, sender, subject,
                    received_at, bank, status, raw_excerpt
                )
                VALUES (%s, 'gmail', %s, %s, %s, %s, %s, %s, 'processed', %s)
                RETURNING id
                """,
                (
                    user_id,
                    provider_message_id,
                    email_fp,
                    sender,
                    subject,
                    received_at,
                    parsed["bank"],
                    body[:1200],
                ),
            ).fetchone()
            email_message_id = int(email_row["id"])
        parsed = _enrich_candidate_with_card_alias(conn, user_id, parsed)

        if parsed.get("email_kind") == "statement":
            parsed["category"] = "Estado de cuenta"
        else:
            parsed["category"] = normalize_category(parsed["category"], parsed["transaction_type"])

        if parsed.get("email_kind") == "statement":
            candidate_status = "pending"
            transaction_id = None
            review_reason = parsed["confidence_reason"]
        elif _transaction_duplicate_exists(conn, user_id, parsed):
            candidate_status = "duplicate"
            transaction_id = None
            review_reason = "Transacción idéntica ya existe."
        elif False and auto_commit and float(parsed["confidence"]) >= AUTO_COMMIT_CONFIDENCE and float(parsed.get("amount") or 0) > 0:
            transaction_id = _insert_transaction(conn, user_id, parsed)
            candidate_status = "auto_saved"
            review_reason = "Guardada automáticamente por alta confianza."
        else:
            transaction_id = None
            candidate_status = "pending"
            review_reason = parsed["confidence_reason"]

        candidate_row = conn.execute(
            """
            INSERT INTO email_transaction_candidates (
                user_id, email_message_id, fingerprint, transaction_id,
                transaction_date, description, amount, transaction_type,
                category, account, source, notes, original_amount, original_currency,
                exchange_rate, confidence, status, review_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, fingerprint)
            DO UPDATE SET updated_at = NOW()
            RETURNING *
            """,
            (
                user_id,
                email_message_id,
                candidate_fp,
                transaction_id,
                parsed["transaction_date"],
                parsed["description"],
                parsed["amount"],
                parsed["transaction_type"],
                parsed["category"],
                parsed["account"],
                parsed["source"],
                parsed["notes"],
                parsed["original_amount"],
                parsed["original_currency"],
                parsed["exchange_rate"],
                parsed["confidence"],
                candidate_status,
                review_reason,
            ),
        ).fetchone()

        if parsed.get("email_kind") == "statement":
            conn.execute(
                """
                INSERT INTO email_statement_documents (
                    user_id, email_message_id, bank, subject, statement_month,
                    received_at, attachment_names, extracted_text_excerpt, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending_reconciliation')
                ON CONFLICT (user_id, email_message_id)
                DO UPDATE SET
                    statement_month = EXCLUDED.statement_month,
                    attachment_names = EXCLUDED.attachment_names,
                    extracted_text_excerpt = EXCLUDED.extracted_text_excerpt,
                    updated_at = NOW()
                """,
                (
                    user_id,
                    email_message_id,
                    parsed["bank"],
                    subject,
                    parsed.get("statement_month"),
                    received_at,
                    parsed.get("attachment_names") or [],
                    (body or "")[:2500],
                ),
            )

        conn.commit()

    return {
        "status": "OK",
        "message": "Correo analizado.",
        "candidate": dict(candidate_row),
    }


def list_email_candidates(status_filter: str | None = None, limit: int = 50) -> dict[str, Any]:
    _require_owner_user()
    user_id = get_current_user_id()

    where = "WHERE user_id = %s"
    params: list[Any] = [user_id]
    if status_filter:
        where += " AND status = %s"
        params.append(status_filter)

    params.append(limit)

    with get_connection() as conn:
        ensure_email_tables(conn)
        rows = conn.execute(
            f"""
            SELECT *
            FROM email_transaction_candidates
            {where}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()
        conn.commit()

    return {"status": "OK", "items": [dict(row) for row in rows]}


def decide_candidate(candidate_id: int, decision: str) -> dict[str, Any]:
    _require_owner_user()
    user_id = get_current_user_id()
    decision_clean = (decision or "").lower().strip()

    with get_connection() as conn:
        ensure_email_tables(conn)
        row = conn.execute(
            """
            SELECT *
            FROM email_transaction_candidates
            WHERE id = %s AND user_id = %s
            """,
            (candidate_id, user_id),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Candidato no encontrado.")

        candidate = dict(row)

        if decision_clean in {"reject", "rechazar", "rejected"}:
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'rejected', updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (candidate_id, user_id),
            )
            conn.commit()
            return {"status": "OK", "message": "Candidato rechazado."}

        if decision_clean not in {"confirm", "confirmar", "guardar", "save"}:
            raise HTTPException(status_code=400, detail="Decisión inválida.")

        if candidate.get("transaction_id"):
            return {"status": "OK", "message": "Ya estaba guardado.", "transaction_id": candidate["transaction_id"]}

        if candidate.get("transaction_type") == "statement":
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'confirmed', updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (candidate_id, user_id),
            )
            conn.commit()
            return {"status": "OK", "message": "Estado de cuenta marcado como revisado."}

        transaction_id = _insert_transaction(conn, user_id, candidate)
        conn.execute(
            """
            UPDATE email_transaction_candidates
            SET status = 'confirmed', transaction_id = %s, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (transaction_id, candidate_id, user_id),
        )
        conn.commit()

    return {"status": "OK", "message": "Movimiento guardado.", "transaction_id": transaction_id}


def _decode_gmail_body(payload: dict[str, Any]) -> str:
    chunks: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body") or {}
        data = body.get("data")

        if data and mime in {"text/plain", "text/html"}:
            try:
                raw = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
                if mime == "text/html":
                    raw = re.sub(r"(?i)<\s*(br|/tr|/td|/p|/div|/li)\b[^>]*>", "\n", raw)
                    raw = re.sub(r"<[^>]+>", " ", raw)
                raw = html.unescape(raw).replace("&nbsp;", " ")
                raw = re.sub(r"[ \t]+", " ", raw)
                raw = re.sub(r"\n\s+", "\n", raw)
                chunks.append(raw.strip())
            except Exception:
                pass

        for child in part.get("parts") or []:
            walk(child)

    walk(payload or {})
    return "\n".join(chunk for chunk in chunks if chunk)


def _collect_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []

    def walk(part: dict[str, Any]) -> None:
        filename = part.get("filename") or ""
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        mime = part.get("mimeType", "")
        if filename or attachment_id:
            attachments.append({
                "filename": filename,
                "attachment_id": attachment_id,
                "mime_type": mime,
                "size": body.get("size"),
            })
        for child in part.get("parts") or []:
            walk(child)

    walk(payload or {})
    return attachments


def _extract_pdf_attachment_text(gmail_service, message_id: str, attachments: list[dict[str, Any]]) -> tuple[str, list[str]]:
    texts: list[str] = []
    names: list[str] = []
    try:
        from pypdf import PdfReader
    except Exception:
        return "", [a.get("filename") or "" for a in attachments if a.get("filename")]

    for attachment in attachments:
        filename = attachment.get("filename") or ""
        attachment_id = attachment.get("attachment_id")
        mime_type = attachment.get("mime_type") or ""
        if filename:
            names.append(filename)
        if not attachment_id:
            continue
        if "pdf" not in mime_type.lower() and not filename.lower().endswith(".pdf"):
            continue
        try:
            data = gmail_service.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute().get("data")
            if not data:
                continue
            raw = base64.urlsafe_b64decode(data.encode("utf-8"))
            reader = PdfReader(BytesIO(raw))
            page_texts = []
            for page in reader.pages[:8]:
                page_texts.append(page.extract_text() or "")
            text = "\n".join(page_texts).strip()
            if text:
                texts.append(f"[PDF {filename}]\n{text}")
        except Exception:
            continue
    return "\n".join(texts), names

def _gmail_service():
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except Exception as exc:
        raise RuntimeError(
            "Faltan dependencias Gmail. Instala google-api-python-client y google-auth."
        ) from exc

    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Faltan GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET o GMAIL_REFRESH_TOKEN.")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def sync_gmail_for_owner(max_results: int = 10, auto_commit: bool = False, query: str | None = None, current_month_only: bool = True) -> dict[str, Any]:
    # Fase 6.2: lectura y candidatos pendientes únicamente. No autoguardar.
    auto_commit = False
    service = _gmail_service()
    gmail_query = build_current_month_gmail_query(query or DEFAULT_QUERY) if current_month_only else (query or DEFAULT_QUERY)

    with get_connection() as conn:
        ensure_email_tables(conn)
        owner_id = _owner_user_id(conn)
        if not owner_id:
            raise RuntimeError("No encontré usuario owner para guardar correos.")
        conn.commit()

    response = service.users().messages().list(
        userId="me",
        q=gmail_query,
        maxResults=max_results,
    ).execute()

    messages = response.get("messages", []) or []
    processed = []

    for item in messages:
        message_id = item.get("id")
        full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        headers = {h.get("name", "").lower(): h.get("value", "") for h in full.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        sender = headers.get("from", "")
        date_header = headers.get("date")
        received_at = None
        if date_header:
            try:
                received_at = parsedate_to_datetime(date_header).astimezone(timezone.utc).isoformat()
            except Exception:
                received_at = None

        payload = full.get("payload", {})
        body = _decode_gmail_body(payload) or full.get("snippet", "")
        attachments = _collect_attachments(payload)
        pdf_text, attachment_names = _extract_pdf_attachment_text(service, message_id, attachments)
        if pdf_text:
            body = f"{body}\n\n{pdf_text}"
        result = scan_email_text(
            subject=subject,
            sender=sender,
            body=body,
            received_at=received_at,
            auto_commit=auto_commit,
            user_id=owner_id,
            provider_message_id=message_id,
            attachment_names=attachment_names,
        )
        processed.append({
            "gmail_id": message_id,
            "subject": subject,
            "status": result.get("status"),
            "candidate_status": (result.get("candidate") or {}).get("status"),
        })

    with get_connection() as conn:
        ensure_email_tables(conn)
        conn.execute(
            """
            UPDATE email_monitor_settings
            SET last_scan_at = NOW(), updated_at = NOW()
            WHERE user_id = %s
            """,
            (owner_id,),
        )
        conn.commit()

    auto_saved = sum(1 for item in processed if item.get("candidate_status") == "auto_saved")
    pending = sum(1 for item in processed if item.get("candidate_status") == "pending")
    ignored = sum(1 for item in processed if item.get("status") in {"IGNORED_EMAIL", "DUPLICATE_IGNORED_EMAIL"})
    duplicates = sum(1 for item in processed if item.get("status") == "DUPLICATE_EMAIL" or item.get("candidate_status") == "duplicate")

    return {
        "status": "OK",
        "query": gmail_query,
        "found": len(messages),
        "processed": processed,
        "summary": {
            "auto_saved": auto_saved,
            "pending": pending,
            "duplicates": duplicates,
            "ignored": ignored,
        },
        "message": f"Escaneo completado. Encontrados: {len(messages)}, pendientes: {pending}, duplicados: {duplicates}, ignorados: {ignored}. Auto guardado desactivado.",
    }


def cron_sync(secret: str | None, max_results: int = 20) -> dict[str, Any]:
    if not CRON_SECRET:
        raise HTTPException(status_code=503, detail="EMAIL_MONITOR_CRON_SECRET no está configurado.")
    if not secret or secret != CRON_SECRET:
        raise HTTPException(status_code=403, detail="Cron secret inválido.")
    try:
        return sync_gmail_for_owner(max_results=max_results, auto_commit=False, current_month_only=True)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}
