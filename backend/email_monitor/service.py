from __future__ import annotations

import base64
import os
import re
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
    '(from:bac OR from:credomatic OR from:baccredomatic OR from:notificacionesbaccr.com OR from:estadosdecuenta@baccredomatic.cr OR from:popular OR from:bancopopular OR from:multimoney OR "MultiMoney" OR "Banco Popular") ("Notificación de transacción" OR "Notificación de Transferencia" OR "Transacción realizada" OR "confirmación de transferencia" OR compra OR pago OR transferencia OR SINPE OR depósito OR deposito OR retiro OR abono OR débito OR debito OR crédito OR credito OR "estado de cuenta" OR "estados de cuenta") -promoción -promocion -newsletter -publicidad -"sesión se inició" -"sesion se inicio" -"seguro de vida" -"nuevos seguros" -"tasa cero" -"e-scooter"',
)
AUTO_COMMIT_CONFIDENCE = float(os.getenv("EMAIL_AUTO_COMMIT_CONFIDENCE", "0.90"))


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
) -> dict[str, Any]:
    if user_id is None:
        _require_owner_user()
        user_id = get_current_user_id()

    parsed = parse_financial_email(subject, sender, body, received_at)
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
            conn.commit()
            return {
                "status": "DUPLICATE_EMAIL",
                "message": "Correo ya procesado.",
                "candidate": dict(existing_candidate) if existing_candidate else None,
            }

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
        elif auto_commit and float(parsed["confidence"]) >= AUTO_COMMIT_CONFIDENCE and float(parsed.get("amount") or 0) > 0:
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
                raw = raw.replace("&nbsp;", " ").replace("&amp;", "&")
                raw = re.sub(r"[ \t]+", " ", raw)
                raw = re.sub(r"\n\s+", "\n", raw)
                chunks.append(raw.strip())
            except Exception:
                pass

        for child in part.get("parts") or []:
            walk(child)

    walk(payload or {})
    return "\n".join(chunk for chunk in chunks if chunk)


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

        body = _decode_gmail_body(full.get("payload", {})) or full.get("snippet", "")
        result = scan_email_text(
            subject=subject,
            sender=sender,
            body=body,
            received_at=received_at,
            auto_commit=auto_commit,
            user_id=owner_id,
            provider_message_id=message_id,
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
        "message": f"Escaneo completado. Encontrados: {len(messages)}, guardados: {auto_saved}, pendientes: {pending}, duplicados: {duplicates}, ignorados: {ignored}.",
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
