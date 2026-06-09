from __future__ import annotations

import base64
import html
import json
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
from backend.email_monitor.deduplication import canonical_score, find_semantic_duplicate, resolve_transaction_time
from backend.email_monitor.normalization import normalize_description

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "gatotico99@gmail.com")
CRON_SECRET = os.getenv("EMAIL_MONITOR_CRON_SECRET", "")
DEFAULT_QUERY = os.getenv(
    "GMAIL_FINANCE_QUERY",
    # Sender-only query on purpose. The parser decides what is financial.
    # The old query mixed sender + keywords and Gmail returned only a tiny subset.
    '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:alerta@baccredomatic.com OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:info@info.baccredomatic.net OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular.fi.cr OR from:bancopopular OR from:popular)',
)
# Fase 6.2: no se guarda nada automático. Primero validamos lectura limpia.
AUTO_COMMIT_CONFIDENCE = float(os.getenv("EMAIL_AUTO_COMMIT_CONFIDENCE", "999"))


def build_current_month_gmail_query(base_query: str | None = None, today: date | None = None) -> str:
    """Return Gmail query scoped to Kenneth's active card/bank cycle.

    BAC card expenses must be reviewed by cut cycle, not calendar month.
    Default cycle: 21 -> 21. On June 8 this scans May 21 through June 21,
    so May 21-31 purchases are not lost.
    """
    today = today or date.today()
    cut_day = int(os.getenv("BAC_CARD_CUT_DAY", "21") or "21")
    cut_day = max(1, min(cut_day, 28))

    if today.day >= cut_day:
        start = date(today.year, today.month, cut_day)
    else:
        if today.month == 1:
            start = date(today.year - 1, 12, cut_day)
        else:
            start = date(today.year, today.month - 1, cut_day)

    if start.month == 12:
        end = date(start.year + 1, 1, cut_day)
    else:
        end = date(start.year, start.month + 1, cut_day)

    base = (base_query or DEFAULT_QUERY or '').strip()

    # Remove broad recency filters so the cycle range is the source of truth.
    base = re.sub(r"\bnewer_than:\S+", "", base).strip()
    base = re.sub(r"\bafter:\d{4}/\d{1,2}/\d{1,2}", "", base).strip()
    base = re.sub(r"\bbefore:\d{4}/\d{1,2}/\d{1,2}", "", base).strip()

    # Gmail before: is exclusive. Add one day to include the cut day itself.
    before = end + timedelta(days=1)
    return f"{base} after:{start:%Y/%m/%d} before:{before:%Y/%m/%d}".strip()


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
    for ddl in [
        "ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS raw_body TEXT",
        "ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS body_text TEXT",
        "ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
        "ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS attachment_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS parse_reason TEXT",
    ]:
        conn.execute(ddl)

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

    for ddl in [
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_last4 TEXT",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_owner TEXT",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS billing_cycle_start DATE",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS billing_cycle_end DATE",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS dedupe_key TEXT",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS duplicate_of BIGINT",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS canonical_transaction_id BIGINT",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS transaction_time TIME",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS raw_description TEXT",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS normalized_description TEXT",
    ]:
        conn.execute(ddl)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_candidates_card_cycle
        ON email_transaction_candidates(user_id, card_last4, billing_cycle_start, billing_cycle_end)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_candidates_dedupe
        ON email_transaction_candidates(user_id, transaction_date, amount, transaction_type, status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_candidates_semantic_dedupe
        ON email_transaction_candidates(user_id, transaction_date, amount, transaction_time, status)
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_card_settings (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL DEFAULT 1,
            name TEXT NOT NULL DEFAULT 'BAC tarjetas',
            cut_day INTEGER NOT NULL DEFAULT 21,
            payment_day INTEGER NOT NULL DEFAULT 5,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for ddl in [
        "ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS bank TEXT NOT NULL DEFAULT 'bac'",
        "ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS card_last4 TEXT",
        "ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS owner_label TEXT",
        "ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    ]:
        conn.execute(ddl)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_card_settings_user_bank_card
        ON credit_card_settings(user_id, bank, card_last4)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_parser_logs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            email_message_id BIGINT,
            provider_message_id TEXT,
            sender TEXT,
            subject TEXT,
            bank TEXT,
            action TEXT NOT NULL,
            result TEXT,
            reason TEXT,
            extracted_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for ddl in [
        "ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS email_message_id BIGINT",
        "ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS result TEXT",
        "ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS extracted_payload JSONB",
    ]:
        conn.execute(ddl)


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


def _log_email_event(
    conn,
    *,
    user_id: int,
    email_message_id: int | None = None,
    provider_message_id: str | None = None,
    sender: str = "",
    subject: str = "",
    bank: str = "unknown",
    action: str = "info",
    result: str | None = None,
    reason: str = "",
    extracted_payload: dict[str, Any] | None = None,
) -> None:
    """Best-effort audit log for every parser decision.

    action is the coarse route used by the scanner. result is the business
    classification expected by JARVIS: processed, ignored, statement,
    duplicate, or error. Logging must never break ingestion.
    """
    try:
        payload_json = json.dumps(extracted_payload or {}, default=str) if extracted_payload else None
        conn.execute(
            """
            INSERT INTO email_parser_logs (
                user_id, email_message_id, provider_message_id, sender, subject,
                bank, action, result, reason, extracted_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                user_id,
                email_message_id,
                provider_message_id,
                sender,
                subject,
                bank,
                action,
                result or action,
                reason[:1000],
                payload_json,
            ),
        )
    except Exception:
        pass

def _settings_query_for_owner(conn, user_id: int) -> str:
    row = conn.execute(
        """
        INSERT INTO email_monitor_settings (user_id, gmail_query, auto_commit_confidence)
        VALUES (%s, %s, 999)
        ON CONFLICT (user_id) DO UPDATE
        SET gmail_query = CASE
                WHEN email_monitor_settings.gmail_query IS NULL
                  OR email_monitor_settings.gmail_query = ''
                  OR email_monitor_settings.gmail_query LIKE '%%Notificación de transacción%%'
                THEN EXCLUDED.gmail_query
                ELSE email_monitor_settings.gmail_query
            END,
            auto_commit_confidence = 999,
            updated_at = NOW()
        RETURNING gmail_query
        """,
        (user_id, DEFAULT_QUERY),
    ).fetchone()
    return (row or {}).get("gmail_query") or DEFAULT_QUERY


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
            DO UPDATE SET
                gmail_query = CASE
                    WHEN email_monitor_settings.gmail_query IS NULL
                      OR email_monitor_settings.gmail_query = ''
                      OR email_monitor_settings.gmail_query LIKE '%%Notificación de transacción%%'
                    THEN EXCLUDED.gmail_query
                    ELSE email_monitor_settings.gmail_query
                END,
                auto_commit_confidence = 999,
                updated_at = NOW()
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
    last4 = candidate.get("card_last4") or _extract_card_last4_from_account(candidate.get("account"))
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
    relationship = row["relationship"]
    primary = bool(row["is_primary"])
    notes = candidate.get("notes") or ""
    extra = f"titular tarjeta: {owner_label}"
    if relationship:
        extra += f" ({relationship})"
    if primary:
        extra += " | tarjeta principal"
    if extra not in notes:
        candidate["notes"] = f"{notes} | {extra}" if notes else extra
    candidate["card_owner"] = owner_label
    candidate["card_last4"] = last4
    return candidate


def _transaction_duplicate_match(conn, user_id: int, candidate: dict[str, Any]) -> int | None:
    """Return an existing saved transaction id for exact duplicates."""
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
    return int(row["id"]) if row else None


def _candidate_duplicate_match(conn, user_id: int, candidate: dict[str, Any], current_fingerprint: str | None = None):
    """Find the canonical candidate for exact or semantic duplicates.

    Rule business Fase 1.5: exact same amount + same date + ±10 minutes.
    canonical_transaction_id points to the dominant row; duplicate_of is kept
    for backward compatibility with the previous UI.
    """
    dedupe_key = candidate.get("dedupe_key")
    if dedupe_key:
        row = conn.execute(
            """
            SELECT id, description, account, source, created_at
            FROM email_transaction_candidates
            WHERE user_id = %s
              AND dedupe_key = %s
              AND (%s IS NULL OR fingerprint <> %s)
              AND status IN ('pending','confirmed','auto_saved')
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (user_id, dedupe_key, current_fingerprint, current_fingerprint),
        ).fetchone()
        if row:
            return row

    return find_semantic_duplicate(conn, user_id, candidate, current_fingerprint)




def _repair_orphan_duplicate_links(conn, user_id: int) -> int:
    """Backfill duplicate candidates that were marked without a canonical row.

    A duplicate candidate must point to the dominant candidate that represents
    the real movement. The matching rule mirrors Fase 1.5: same user, same
    transaction date, same exact amount (with cents tolerance) and, when both
    rows have a time, a ±10 minute window.

    This repair is intentionally conservative: it only links rows already
    marked as duplicate and only to non-duplicate candidates.
    """
    row = conn.execute(
        """
        WITH ranked_matches AS (
            SELECT
                duplicate_row.id AS duplicate_id,
                canonical_row.id AS canonical_id,
                ROW_NUMBER() OVER (
                    PARTITION BY duplicate_row.id
                    ORDER BY
                        canonical_row.created_at ASC,
                        canonical_row.id ASC
                ) AS match_rank
            FROM email_transaction_candidates duplicate_row
            JOIN email_transaction_candidates canonical_row
              ON canonical_row.user_id = duplicate_row.user_id
             AND canonical_row.id <> duplicate_row.id
             AND canonical_row.transaction_date = duplicate_row.transaction_date
             AND ABS(canonical_row.amount - duplicate_row.amount) < 0.01
             AND canonical_row.status IN ('pending', 'confirmed', 'auto_saved')
             AND (
                    duplicate_row.transaction_time IS NULL
                 OR canonical_row.transaction_time IS NULL
                 OR ABS(EXTRACT(EPOCH FROM (
                        (duplicate_row.transaction_date + duplicate_row.transaction_time)
                      - (canonical_row.transaction_date + canonical_row.transaction_time)
                    ))) <= 600
             )
            WHERE duplicate_row.user_id = %s
              AND duplicate_row.status = 'duplicate'
              AND duplicate_row.canonical_transaction_id IS NULL
        ), repaired AS (
            UPDATE email_transaction_candidates target
            SET canonical_transaction_id = ranked_matches.canonical_id,
                duplicate_of = COALESCE(target.duplicate_of, ranked_matches.canonical_id),
                review_reason = COALESCE(NULLIF(target.review_reason, ''), 'Duplicado semántico vinculado a su transacción canónica.'),
                updated_at = NOW()
            FROM ranked_matches
            WHERE target.id = ranked_matches.duplicate_id
              AND ranked_matches.match_rank = 1
            RETURNING target.id
        )
        SELECT COUNT(*) AS repaired_count
        FROM repaired
        """,
        (user_id,),
    ).fetchone()
    return int((row or {}).get("repaired_count") or 0)


def _assert_duplicate_has_trace(candidate: dict[str, Any]) -> None:
    """Fail fast before committing inconsistent duplicate metadata."""
    if candidate.get("status") != "duplicate":
        return
    if candidate.get("canonical_transaction_id") or candidate.get("duplicate_of") or candidate.get("transaction_id"):
        return
    raise RuntimeError(
        "Duplicate candidate consistency error: status='duplicate' requires "
        "canonical_transaction_id, duplicate_of, or transaction_id."
    )

def _find_existing_ingested(conn, user_id: int, email_fp: str, provider_message_id: str | None):
    if provider_message_id:
        row = conn.execute(
            """
            SELECT id
            FROM email_ingested_messages
            WHERE user_id = %s
              AND provider = 'gmail'
              AND provider_message_id = %s
            LIMIT 1
            """,
            (user_id, provider_message_id),
        ).fetchone()
        if row:
            return row
    return conn.execute(
        """
        SELECT id
        FROM email_ingested_messages
        WHERE user_id = %s
          AND fingerprint = %s
        LIMIT 1
        """,
        (user_id, email_fp),
    ).fetchone()


def _upsert_ingested_message(
    conn,
    *,
    user_id: int,
    provider_message_id: str | None,
    email_fp: str,
    sender: str,
    subject: str,
    received_at: str | None,
    bank: str,
    status: str,
    body: str,
    reason: str = "",
    attachment_names: list[str] | None = None,
) -> int:
    attachment_names = attachment_names or []
    raw_excerpt = (body or reason or "")[:1200]
    raw_body = (body or "")[:20000]
    existing = _find_existing_ingested(conn, user_id, email_fp, provider_message_id)
    if existing:
        email_id = int(existing["id"])
        conn.execute(
            """
            UPDATE email_ingested_messages
            SET provider_message_id = COALESCE(%s, provider_message_id),
                fingerprint = %s,
                sender = %s,
                subject = %s,
                received_at = COALESCE(%s, received_at),
                bank = %s,
                status = %s,
                raw_excerpt = %s,
                raw_body = %s,
                body_text = %s,
                attachment_names = %s,
                attachment_count = %s,
                parse_reason = %s
            WHERE id = %s AND user_id = %s
            """,
            (
                provider_message_id,
                email_fp,
                sender,
                subject,
                received_at,
                bank,
                status,
                raw_excerpt,
                raw_body,
                raw_body,
                attachment_names,
                len(attachment_names),
                reason[:1000],
                email_id,
                user_id,
            ),
        )
        return email_id

    row = conn.execute(
        """
        INSERT INTO email_ingested_messages (
            user_id, provider, provider_message_id, fingerprint, sender, subject,
            received_at, bank, status, raw_excerpt, raw_body, body_text,
            attachment_names, attachment_count, parse_reason
        )
        VALUES (%s, 'gmail', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, provider, provider_message_id)
        DO UPDATE SET
            fingerprint = EXCLUDED.fingerprint,
            sender = EXCLUDED.sender,
            subject = EXCLUDED.subject,
            received_at = COALESCE(EXCLUDED.received_at, email_ingested_messages.received_at),
            bank = EXCLUDED.bank,
            status = EXCLUDED.status,
            raw_excerpt = EXCLUDED.raw_excerpt,
            raw_body = EXCLUDED.raw_body,
            body_text = EXCLUDED.body_text,
            attachment_names = EXCLUDED.attachment_names,
            attachment_count = EXCLUDED.attachment_count,
            parse_reason = EXCLUDED.parse_reason
        RETURNING id
        """,
        (
            user_id,
            provider_message_id,
            email_fp,
            sender,
            subject,
            received_at,
            bank,
            status,
            raw_excerpt,
            raw_body,
            raw_body,
            attachment_names,
            len(attachment_names),
            reason[:1000],
        ),
    ).fetchone()
    return int(row["id"])


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
    attachment_names = attachment_names or []
    parsed["attachment_names"] = attachment_names
    email_fp = fingerprint_email(sender, subject, body, received_at)

    with get_connection() as conn:
        ensure_email_tables(conn)
        email_message_id = _upsert_ingested_message(
            conn,
            user_id=user_id,
            provider_message_id=provider_message_id,
            email_fp=email_fp,
            sender=sender,
            subject=subject,
            received_at=received_at,
            bank=parsed.get("bank") or "unknown",
            status=("ignored" if parsed.get("email_kind") == "ignored" else "statement" if parsed.get("email_kind") == "statement" else "processed"),
            body=body,
            reason=parsed.get("ignore_reason") or parsed.get("confidence_reason") or "",
            attachment_names=attachment_names,
        )

        if parsed.get("email_kind") == "ignored":
            _log_email_event(
                conn,
                user_id=user_id,
                email_message_id=email_message_id,
                provider_message_id=provider_message_id,
                sender=sender,
                subject=subject,
                bank=parsed.get("bank") or "unknown",
                action="ignored",
                result="ignored",
                extracted_payload=parsed,
                reason=parsed.get("ignore_reason") or parsed.get("confidence_reason") or "Correo ignorado.",
            )
            conn.commit()
            return {
                "status": "IGNORED_EMAIL",
                "message": parsed.get("ignore_reason") or "Correo ignorado.",
                "ignored": True,
                "candidate": None,
            }

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
                    bank = EXCLUDED.bank,
                    subject = EXCLUDED.subject,
                    statement_month = EXCLUDED.statement_month,
                    received_at = COALESCE(EXCLUDED.received_at, email_statement_documents.received_at),
                    attachment_names = EXCLUDED.attachment_names,
                    extracted_text_excerpt = EXCLUDED.extracted_text_excerpt,
                    status = 'pending_reconciliation',
                    updated_at = NOW()
                """,
                (
                    user_id,
                    email_message_id,
                    parsed["bank"],
                    subject,
                    parsed.get("statement_month"),
                    received_at,
                    attachment_names,
                    (body or "")[:2500],
                ),
            )
            # Remove old zero-amount statement candidates if this message had any.
            conn.execute(
                """
                DELETE FROM email_transaction_candidates
                WHERE user_id = %s
                  AND email_message_id = %s
                  AND transaction_type = 'statement'
                """,
                (user_id, email_message_id),
            )
            _log_email_event(
                conn,
                user_id=user_id,
                email_message_id=email_message_id,
                provider_message_id=provider_message_id,
                sender=sender,
                subject=subject,
                bank=parsed.get("bank") or "unknown",
                action="statement_document",
                result="statement",
                extracted_payload=parsed,
                reason=parsed.get("confidence_reason") or "Estado de cuenta guardado como documento.",
            )
            conn.commit()
            return {
                "status": "STATEMENT_DOCUMENT",
                "message": "Estado de cuenta guardado como documento pendiente de conciliación.",
                "candidate": None,
                "statement": True,
            }

        parsed = _enrich_candidate_with_card_alias(conn, user_id, parsed)

        raw_description = parsed.get("description") or ""
        normalized_description = normalize_description(raw_description)
        parsed["raw_description"] = raw_description
        parsed["normalized_description"] = normalized_description
        parsed["description"] = normalized_description[:240]
        parsed["transaction_time"] = resolve_transaction_time(parsed)
        if raw_description and normalized_description and raw_description.strip() != normalized_description:
            note = f"descripción original: {raw_description[:180]}"
            parsed["notes"] = f"{parsed.get('notes') or ''} | {note}" if parsed.get("notes") else note

        # One Gmail message should map to one stable candidate. The older
        # fingerprint used only date+amount+merchant, so two real purchases from
        # the same merchant on the same day collapsed into one row. Prefer the
        # Gmail id + parser dedupe key; fallback keeps manual scan-text stable.
        if provider_message_id:
            fp_base = f"{user_id}|gmail|{provider_message_id}|{parsed.get('dedupe_key') or ''}"
            import hashlib
            candidate_fp = hashlib.sha256(fp_base.encode("utf-8")).hexdigest()
        else:
            candidate_fp = fingerprint_candidate(
                user_id=user_id,
                transaction_date=parsed["transaction_date"],
                amount=float(parsed["amount"]),
                transaction_type=parsed["transaction_type"],
                description=parsed["description"],
                bank=parsed["bank"],
            )
        parsed["category"] = normalize_category(parsed["category"], parsed["transaction_type"])

        duplicate_candidate = _candidate_duplicate_match(conn, user_id, parsed, candidate_fp)
        replace_existing_duplicate = False
        existing_transaction_id = _transaction_duplicate_match(conn, user_id, parsed)
        if existing_transaction_id:
            candidate_status = "duplicate"
            transaction_id = existing_transaction_id
            duplicate_of = None
            review_reason = "Transacción idéntica ya existe en movimientos guardados."
        elif duplicate_candidate:
            incoming_score = canonical_score(parsed.get("description") or "", parsed.get("account"), parsed.get("source"))
            existing_score = canonical_score(duplicate_candidate["description"], duplicate_candidate["account"], duplicate_candidate["source"])
            transaction_id = None
            if incoming_score > existing_score:
                candidate_status = "pending"
                duplicate_of = None
                replace_existing_duplicate = True
                review_reason = "Candidato canónico: versión más específica del mismo movimiento detectado por otro correo/banco."
            else:
                candidate_status = "duplicate"
                duplicate_of = int(duplicate_candidate["id"])
                review_reason = "Posible duplicado del mismo movimiento ya detectado por otro correo/banco."
        else:
            transaction_id = None
            duplicate_of = None
            candidate_status = "pending"
            review_reason = parsed["confidence_reason"]

        canonical_candidate_id = duplicate_of
        candidate_row = conn.execute(
            """
            INSERT INTO email_transaction_candidates (
                user_id, email_message_id, fingerprint, transaction_id,
                transaction_date, description, amount, transaction_type,
                category, account, source, notes, original_amount, original_currency,
                exchange_rate, card_last4, card_owner, billing_cycle_start,
                billing_cycle_end, dedupe_key, duplicate_of, canonical_transaction_id,
                transaction_time, raw_description, normalized_description, confidence, status, review_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, fingerprint)
            DO UPDATE SET
                email_message_id = EXCLUDED.email_message_id,
                transaction_date = EXCLUDED.transaction_date,
                description = EXCLUDED.description,
                amount = EXCLUDED.amount,
                transaction_type = EXCLUDED.transaction_type,
                category = EXCLUDED.category,
                account = EXCLUDED.account,
                notes = EXCLUDED.notes,
                original_amount = EXCLUDED.original_amount,
                original_currency = EXCLUDED.original_currency,
                exchange_rate = EXCLUDED.exchange_rate,
                card_last4 = EXCLUDED.card_last4,
                card_owner = EXCLUDED.card_owner,
                billing_cycle_start = EXCLUDED.billing_cycle_start,
                billing_cycle_end = EXCLUDED.billing_cycle_end,
                dedupe_key = EXCLUDED.dedupe_key,
                duplicate_of = EXCLUDED.duplicate_of,
                canonical_transaction_id = EXCLUDED.canonical_transaction_id,
                transaction_time = EXCLUDED.transaction_time,
                raw_description = EXCLUDED.raw_description,
                normalized_description = EXCLUDED.normalized_description,
                confidence = EXCLUDED.confidence,
                status = CASE
                    WHEN email_transaction_candidates.status IN ('confirmed','auto_saved')
                    THEN email_transaction_candidates.status
                    ELSE EXCLUDED.status
                END,
                review_reason = EXCLUDED.review_reason,
                updated_at = NOW()
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
                parsed.get("exchange_rate"),
                parsed.get("card_last4"),
                parsed.get("card_owner"),
                parsed.get("billing_cycle_start"),
                parsed.get("billing_cycle_end"),
                parsed.get("dedupe_key"),
                duplicate_of,
                duplicate_of,
                parsed.get("transaction_time"),
                parsed.get("raw_description"),
                parsed.get("normalized_description"),
                parsed["confidence"],
                candidate_status,
                review_reason,
            ),
        ).fetchone()
        candidate_row = dict(candidate_row) if candidate_row else {}

        # Persistencia defensiva de la relación canónica. La detección de
        # duplicados y la escritura de la fila no pueden quedar desacopladas:
        # status='duplicate' sin canonical_transaction_id rompe auditoría y UI.
        if candidate_status == "duplicate" and canonical_candidate_id:
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET duplicate_of = %s,
                    canonical_transaction_id = %s,
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                  AND status = 'duplicate'
                """,
                (int(canonical_candidate_id), int(canonical_candidate_id), int(candidate_row["id"]), user_id),
            )
            candidate_row["duplicate_of"] = int(canonical_candidate_id)
            candidate_row["canonical_transaction_id"] = int(canonical_candidate_id)

        if candidate_status != "duplicate" and candidate_row and not candidate_row.get("canonical_transaction_id"):
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET canonical_transaction_id = id, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (int(candidate_row["id"]), user_id),
            )
            candidate_row["canonical_transaction_id"] = candidate_row["id"]

        if replace_existing_duplicate and duplicate_candidate and candidate_row:
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'duplicate',
                    duplicate_of = %s,
                    canonical_transaction_id = %s,
                    review_reason = 'Duplicado semántico: existe una versión canónica más específica.',
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (int(candidate_row["id"]), int(candidate_row["id"]), int(duplicate_candidate["id"]), user_id),
            )

        # Backfill histórico y defensa adicional para corridas reentrantes.
        _repair_orphan_duplicate_links(conn, user_id)
        refreshed_row = conn.execute(
            """
            SELECT *
            FROM email_transaction_candidates
            WHERE id = %s AND user_id = %s
            """,
            (int(candidate_row["id"]), user_id),
        ).fetchone()
        candidate_row = dict(refreshed_row) if refreshed_row else candidate_row
        _assert_duplicate_has_trace(candidate_row)
        _log_email_event(
            conn,
            user_id=user_id,
            email_message_id=email_message_id,
            provider_message_id=provider_message_id,
            sender=sender,
            subject=subject,
            bank=parsed.get("bank") or "unknown",
            action="candidate",
            result=candidate_status,
            extracted_payload=parsed,
            reason=review_reason,
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


def _list_gmail_messages(service, *, gmail_query: str, max_results: int) -> list[dict[str, Any]]:
    """List Gmail messages with pagination.

    Gmail returns pages. The previous scanner processed only the first page and
    the UI sent low max_results values, causing JARVIS to ingest only a handful
    of emails while Gmail had dozens. This function keeps fetching pages until
    the requested cap is reached.
    """
    max_results = max(1, min(int(max_results or 100), 500))
    messages: list[dict[str, Any]] = []
    page_token: str | None = None
    while len(messages) < max_results:
        batch_size = min(100, max_results - len(messages))
        request: dict[str, Any] = {
            "userId": "me",
            "q": gmail_query,
            "maxResults": batch_size,
        }
        if page_token:
            request["pageToken"] = page_token
        response = service.users().messages().list(**request).execute()
        messages.extend(response.get("messages", []) or [])
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return messages[:max_results]


def sync_gmail_for_owner(max_results: int = 100, auto_commit: bool = False, query: str | None = None, current_month_only: bool = True) -> dict[str, Any]:
    # Lectura y candidatos pendientes únicamente. No autoguardar.
    auto_commit = False
    service = _gmail_service()

    with get_connection() as conn:
        ensure_email_tables(conn)
        owner_id = _owner_user_id(conn)
        if not owner_id:
            raise RuntimeError("No encontré usuario owner para guardar correos.")
        settings_query = _settings_query_for_owner(conn, owner_id)
        conn.commit()

    # Do not let the UI's old max_results=25 starve the scanner. Current-month
    # financial inboxes can easily have more than 25 BAC/SINPE/MultiMoney emails.
    effective_max_results = max(int(max_results or 0), 150)
    base_query = (query or settings_query or DEFAULT_QUERY).strip()
    gmail_query = build_current_month_gmail_query(base_query) if current_month_only else base_query

    messages = _list_gmail_messages(service, gmail_query=gmail_query, max_results=effective_max_results)
    processed: list[dict[str, Any]] = []

    for item in messages:
        message_id = item.get("id")
        if not message_id:
            continue
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
            body = f"{body}\n\n{pdf_text}".strip()

        try:
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
        except Exception as exc:
            with get_connection() as conn:
                ensure_email_tables(conn)
                _log_email_event(
                    conn,
                    user_id=owner_id,
                    provider_message_id=message_id,
                    sender=sender,
                    subject=subject,
                    bank="unknown",
                    action="error",
                    reason=str(exc),
                )
                conn.commit()
            result = {"status": "ERROR", "message": str(exc), "candidate": None}

        processed.append({
            "gmail_id": message_id,
            "subject": subject,
            "sender": sender,
            "status": result.get("status"),
            "message": result.get("message"),
            "candidate_status": (result.get("candidate") or {}).get("status"),
        })

    with get_connection() as conn:
        ensure_email_tables(conn)
        conn.execute(
            """
            UPDATE email_monitor_settings
            SET last_scan_at = NOW(), updated_at = NOW(), gmail_query = %s, auto_commit_confidence = 999
            WHERE user_id = %s
            """,
            (settings_query or DEFAULT_QUERY, owner_id),
        )
        conn.commit()

    auto_saved = sum(1 for item in processed if item.get("candidate_status") == "auto_saved")
    pending = sum(1 for item in processed if item.get("candidate_status") == "pending")
    statements = sum(1 for item in processed if item.get("status") == "STATEMENT_DOCUMENT")
    ignored = sum(1 for item in processed if item.get("status") in {"IGNORED_EMAIL", "DUPLICATE_IGNORED_EMAIL"})
    duplicates = sum(1 for item in processed if item.get("status") == "DUPLICATE_EMAIL" or item.get("candidate_status") == "duplicate")
    errors = sum(1 for item in processed if item.get("status") == "ERROR")

    return {
        "status": "OK",
        "query": gmail_query,
        "found": len(messages),
        "processed": processed[:100],
        "summary": {
            "auto_saved": auto_saved,
            "pending": pending,
            "statements": statements,
            "duplicates": duplicates,
            "ignored": ignored,
            "errors": errors,
        },
        "message": (
            f"Escaneo completado. Encontrados: {len(messages)}, pendientes: {pending}, "
            f"estados: {statements}, duplicados: {duplicates}, ignorados: {ignored}, errores: {errors}. "
            "Auto guardado desactivado."
        ),
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
