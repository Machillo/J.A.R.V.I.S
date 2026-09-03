from __future__ import annotations

import base64
import html
import hmac
import hashlib
import json
import logging
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
from backend.email_monitor.personal_rules import apply_workspace_email_rules
from backend.email_monitor.statement_reconciliation import reconcile_statement
from backend.email_monitor.payroll_statement import parse_ccss_order_patronal

OWNER_EMAIL = (
    os.getenv("OWNER_EMAIL", "").strip()
    or next((email.strip() for email in os.getenv("OWNER_EMAILS", "").split(",") if email.strip()), "")
).lower()
CRON_SECRET = os.getenv("EMAIL_MONITOR_CRON_SECRET", "")
DEFAULT_QUERY = os.getenv(
    "GMAIL_FINANCE_QUERY",
    # Sender-only query on purpose. The parser decides what is financial.
    # The old query mixed sender + keywords and Gmail returned only a tiny subset.
    '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:alerta@baccredomatic.com OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:info@info.baccredomatic.net OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular.fi.cr OR from:bancopopular OR from:popular OR from:noreply@ccss.sa.cr OR subject:"Generación de Orden Patronal Digital")',
)
# Gmail ingestion is automatic only for high-confidence parser decisions.
AUTO_COMMIT_CONFIDENCE = max(
    0.0,
    min(float(os.getenv("EMAIL_AUTO_COMMIT_CONFIDENCE", "0.95")), 1.0),
)
logger = logging.getLogger(__name__)


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
            UNIQUE(workspace_id, fingerprint),
            UNIQUE(workspace_id, provider, provider_message_id)
        )
        """
    )
    for ddl in [
        "ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS gmail_history_id TEXT",
        "ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS gmail_watch_expiration TIMESTAMPTZ",
        "ALTER TABLE email_monitor_settings ADD COLUMN IF NOT EXISTS gmail_watch_topic TEXT",
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
            UNIQUE(workspace_id, fingerprint)
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
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS auto_commit_allowed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS personal_rule_id BIGINT",
    ]:
        conn.execute(ddl)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_candidates_card_cycle
        ON email_transaction_candidates(workspace_id, card_last4, billing_cycle_start, billing_cycle_end)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_email_candidates_dedupe
        ON email_transaction_candidates(workspace_id, transaction_date, amount, transaction_type, status)
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
            extracted_text TEXT,
            status TEXT NOT NULL DEFAULT 'pending_reconciliation',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, email_message_id)
        )
        """
    )
    conn.execute("ALTER TABLE email_statement_documents ADD COLUMN IF NOT EXISTS extracted_text TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_salary_reports (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            workspace_id UUID NOT NULL,
            email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE SET NULL,
            provider_message_id TEXT,
            period_month TEXT NOT NULL,
            reported_salary NUMERIC NOT NULL,
            trans_previous_salary NUMERIC,
            previous_salary NUMERIC,
            daily_subsidy NUMERIC,
            employer_number TEXT,
            verification_code TEXT,
            source TEXT NOT NULL DEFAULT 'ccss_order_patronal',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, period_month),
            UNIQUE(workspace_id, provider_message_id)
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
            UNIQUE(workspace_id, card_last4)
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

    for table_name in [
        "email_monitor_settings",
        "email_ingested_messages",
        "email_transaction_candidates",
        "email_statement_documents",
        "card_aliases",
        "email_parser_logs",
    ]:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS workspace_id UUID")


def _owner_user_id(conn) -> int | None:
    if not OWNER_EMAIL:
        raise RuntimeError("OWNER_EMAIL no está configurado.")
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



def _workspace_id_for_user(conn, user_id: int) -> str:
    row = conn.execute(
        """
        SELECT w.id
        FROM accounts a
        JOIN workspaces w
          ON w.owner_account_id = a.id
         AND w.workspace_type = 'personal'
        WHERE a.legacy_allowed_user_id = %s
        ORDER BY w.created_at, w.id
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"No workspace personal found for legacy user_id={user_id}.")
    return str(row["id"])

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
        workspace_id = _workspace_id_for_user(conn, user_id)
        payload_json = json.dumps(extracted_payload or {}, default=str) if extracted_payload else None
        conn.execute(
            """
            INSERT INTO email_parser_logs (
                user_id, workspace_id, email_message_id, provider_message_id, sender, subject,
                bank, action, result, reason, extracted_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                user_id,
                workspace_id,
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
        logger.exception(
            "Could not persist email parser log action=%s result=%s provider_message_id=%s",
            action,
            result or action,
            provider_message_id,
        )


def _candidate_reference(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    for value in [candidate.get("dedupe_key"), candidate.get("notes"), candidate.get("confidence_reason")]:
        match = re.search(r"(?:referencia[: ]*|\|)(\d{8,})", str(value or ""), re.I)
        if match:
            return match.group(1)
    return None


def _candidate_is_internal(candidate: dict[str, Any] | None) -> bool:
    if not candidate:
        return False
    if candidate.get("transaction_type") == "internal_transfer":
        return True
    text = " ".join(str(candidate.get(key) or "") for key in ["description", "category", "notes", "ignore_reason", "confidence_reason"]).lower()
    return "movimiento interno" in text or "cuentas propias" in text or "inversión propia" in text or "inversion propia" in text


def _internal_mirror_exists(conn, workspace_id: str, candidate: dict[str, Any]) -> bool:
    """Detect already-ignored counterpart emails for the same internal transfer.

    BAC and MultiMoney send separate mirror notifications for one movement. If
    the MultiMoney/BAC mirror was already ignored as internal, the later BAC
    SINPE candidate with the same bank reference must not appear for
    manual approval.
    """
    reference = _candidate_reference(candidate)
    if not reference:
        return False
    row = conn.execute(
        """
        SELECT 1
        FROM email_parser_logs
        WHERE workspace_id = %s
          AND result = 'ignored'
          AND extracted_payload::text ILIKE %s
          AND (reason ILIKE '%%intern%%' OR extracted_payload::text ILIKE '%%internal_transfer%%' OR extracted_payload::text ILIKE '%%Movimiento interno%%')
        LIMIT 1
        """,
        (workspace_id, f"%{reference}%"),
    ).fetchone()
    if row is not None:
        return True

    # BAC and MultiMoney may omit the counterparty account in one template.
    # Their shared bank reference plus opposite directions is still a strong,
    # deterministic signal that both emails describe the same own-account move.
    direction = str(candidate.get("movement_direction") or "unknown")
    bank = str(candidate.get("bank") or "unknown")
    if direction not in {"in", "out"} or bank not in {"bac", "multimoney"}:
        return False
    opposite = "out" if direction == "in" else "in"
    row = conn.execute(
        """
        SELECT 1
        FROM email_transaction_candidates c
        JOIN email_ingested_messages m ON m.id = c.email_message_id
        WHERE c.workspace_id = %s
          AND c.transaction_id IS NULL
          AND c.status IN ('pending', 'duplicate')
          AND m.bank IN ('bac', 'multimoney')
          AND m.bank <> %s
          AND c.notes ILIKE %s
          AND c.dedupe_key LIKE %s
        LIMIT 1
        """,
        (workspace_id, bank, f"%{reference}%", f"%|{opposite}"),
    ).fetchone()
    return row is not None


def _delete_pending_internal_mirrors(conn, workspace_id: str, internal_candidate: dict[str, Any]) -> int:
    """Remove pending candidate mirrors after an internal counterpart is found.

    This keeps the review inbox clean when Gmail returns BAC before MultiMoney
    or vice versa. Only pending candidates are removed; confirmed data is never
    touched.
    """
    reference = _candidate_reference(internal_candidate)
    if not reference:
        return 0
    rows = conn.execute(
        """
        DELETE FROM email_transaction_candidates
        WHERE workspace_id = %s
          AND status IN ('pending', 'duplicate')
          AND transaction_id IS NULL
          AND notes ILIKE %s
        RETURNING id, email_message_id
        """,
        (workspace_id, f"%{reference}%"),
    ).fetchall()
    message_ids = [int(row["email_message_id"]) for row in rows if row.get("email_message_id")]
    if message_ids:
        conn.execute(
            """
            UPDATE email_ingested_messages
            SET status = 'ignored',
                parse_reason = 'Movimiento espejo de una transferencia interna ya detectada.'
            WHERE workspace_id = %s AND id = ANY(%s)
            """,
            (workspace_id, message_ids),
        )
    return len(rows)


def _repair_historical_cross_bank_mirrors(conn, workspace_id: str) -> int:
    """Remove old BAC/MultiMoney candidates that share one bank reference.

    Reprocessing an already-ingested Gmail message is not a reliable migration
    mechanism: old rows may preserve parser decisions from an earlier deploy.
    Repair the review inbox directly, but only when bank, reference, date,
    amount and opposite directions all agree.
    """
    rows = conn.execute(
        """
        SELECT c.id, c.email_message_id, c.transaction_date, c.amount,
               c.notes, c.dedupe_key, m.bank
        FROM email_transaction_candidates c
        JOIN email_ingested_messages m ON m.id = c.email_message_id
        WHERE c.workspace_id = %s
          AND c.transaction_id IS NULL
          AND c.status IN ('pending', 'duplicate')
          AND m.bank IN ('bac', 'multimoney')
          AND c.notes ILIKE '%%referencia%%'
        """,
        (workspace_id,),
    ).fetchall()
    grouped: dict[tuple[str, str, float], list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        reference = _candidate_reference(row)
        if not reference:
            continue
        key = (reference, str(row.get("transaction_date")), round(float(row.get("amount") or 0), 2))
        grouped.setdefault(key, []).append(row)

    remove_ids: set[int] = set()
    message_ids: set[int] = set()
    for matches in grouped.values():
        for left in matches:
            left_direction = str(left.get("dedupe_key") or "").rsplit("|", 1)[-1]
            for right in matches:
                if left["id"] == right["id"] or left.get("bank") == right.get("bank"):
                    continue
                right_direction = str(right.get("dedupe_key") or "").rsplit("|", 1)[-1]
                if {left_direction, right_direction} != {"in", "out"}:
                    continue
                remove_ids.update([int(left["id"]), int(right["id"])])
                if left.get("email_message_id"):
                    message_ids.add(int(left["email_message_id"]))
                if right.get("email_message_id"):
                    message_ids.add(int(right["email_message_id"]))

    if not remove_ids:
        return 0
    conn.execute(
        "DELETE FROM email_transaction_candidates WHERE workspace_id = %s AND id = ANY(%s)",
        (workspace_id, list(remove_ids)),
    )
    if message_ids:
        conn.execute(
            """
            UPDATE email_ingested_messages
            SET status = 'ignored',
                parse_reason = 'Movimiento espejo BAC/MultiMoney conciliado por referencia bancaria.'
            WHERE workspace_id = %s AND id = ANY(%s)
            """,
            (workspace_id, list(message_ids)),
        )
    return len(remove_ids)


def _scheduled_commitment_match(conn, workspace_id: str, candidate: dict[str, Any]) -> tuple[int | None, str] | None:
    """Match email evidence to commitments JARVIS already materializes.

    These emails confirm cash movements; they must not create a second ledger
    transaction when the monthly debt/fixed-expense engines already account for
    the same obligation.
    """
    description = str(candidate.get("description") or "").strip().lower()
    amount = round(float(candidate.get("amount") or 0), 2)
    transaction_date = candidate.get("transaction_date")
    if not transaction_date or amount <= 0:
        return None

    if "pago" in description and "multimoney" in description:
        row = conn.execute(
            """
            SELECT id
            FROM transactions
            WHERE workspace_id = %s
              AND source = 'auto_debt_schedule'
              AND ABS(amount - %s) <= GREATEST(1000, %s * 0.05)
              AND transaction_date::date BETWEEN (%s::date - INTERVAL '7 days') AND (%s::date + INTERVAL '7 days')
            ORDER BY
                CASE WHEN LOWER(description) LIKE '%%multi%%' OR LOWER(category) LIKE '%%multi%%' THEN 0 ELSE 1 END,
                ABS(transaction_date::date - %s::date),
                ABS(amount - %s),
                id DESC
            LIMIT 1
            """,
            (workspace_id, amount, amount, transaction_date, transaction_date, transaction_date, amount),
        ).fetchone()
        if row:
            return int(row["id"]), "Comprobante del pago automático de la deuda MultiMoney; no se duplica en finanzas."

    if "casa" in description and "prestamo" in description:
        fixed = conn.execute(
            """
            SELECT expected_amount
            FROM fixed_expenses
            WHERE workspace_id = %s AND is_active = TRUE AND LOWER(TRIM(name)) = 'casa'
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        debt = conn.execute(
            """
            SELECT id, monthly_payment
            FROM debts
            WHERE workspace_id = %s
              AND (LOWER(name) LIKE '%%pap%%' OR LOWER(debt_type) LIKE '%%familiar%%')
            ORDER BY id
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        expected = round(float((fixed or {}).get("expected_amount") or 0) + float((debt or {}).get("monthly_payment") or 0), 2)
        if expected > 0 and abs(expected - amount) < 0.02:
            tx = None
            if debt:
                tx = conn.execute(
                    """
                    SELECT id FROM transactions
                    WHERE workspace_id = %s AND source = 'auto_debt_schedule'
                      AND notes LIKE %s
                      AND DATE_TRUNC('month', transaction_date) = DATE_TRUNC('month', %s::date)
                    ORDER BY id DESC LIMIT 1
                    """,
                    (workspace_id, f"debt_id:{int(debt['id'])};%", transaction_date),
                ).fetchone()
            return (int(tx["id"]) if tx else None), "Comprobante combinado de Casa y préstamo de papá, ya contemplados por sus calendarios automáticos."

    return None


def _repair_historical_scheduled_commitments(conn, workspace_id: str) -> int:
    """Reconcile pending rows created before scheduled matching existed."""
    rows = conn.execute(
        """
        SELECT *
        FROM email_transaction_candidates
        WHERE workspace_id = %s
          AND status = 'pending'
          AND transaction_id IS NULL
        ORDER BY id
        """,
        (workspace_id,),
    ).fetchall()
    repaired = 0
    for raw in rows:
        candidate = dict(raw)
        match = _scheduled_commitment_match(conn, workspace_id, candidate)
        if not match:
            continue
        transaction_id, reason = match
        conn.execute(
            """
            UPDATE email_transaction_candidates
            SET status = 'duplicate',
                transaction_id = %s,
                canonical_transaction_id = CASE
                    WHEN %s IS NULL THEN id
                    ELSE canonical_transaction_id
                END,
                review_reason = %s,
                updated_at = NOW()
            WHERE workspace_id = %s AND id = %s AND status = 'pending'
            """,
            (transaction_id, transaction_id, reason, workspace_id, int(candidate["id"])),
        )
        repaired += 1
    return repaired

def _seed_default_card_aliases(conn, user_id: int, workspace_id: str | None = None) -> None:
    workspace_id = workspace_id or _workspace_id_for_user(conn, user_id)
    """Keep known BAC additional cards owner-aware.

    Kenneth's cards stay in the catalog as primary cards for parsing, but the
    Additional Cards UI filters them out. Emily and Sidey are the only default
    additional-card owners shown there.
    """
    try:
        configured = json.loads(os.getenv("JARVIS_CARD_ALIASES", "[]") or "[]")
    except json.JSONDecodeError:
        configured = []
    defaults = [
        (
            str(item.get("last4") or ""),
            str(item.get("owner") or ""),
            str(item.get("relationship") or "principal"),
            bool(item.get("is_primary", False)),
        )
        for item in configured
        if isinstance(item, dict) and item.get("last4") and item.get("owner")
    ]
    for last4, owner, relationship, is_primary in defaults:
        conn.execute(
            """
            INSERT INTO card_aliases (user_id, workspace_id, card_last4, owner_label, relationship, is_primary)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, card_last4) DO UPDATE
            SET owner_label = EXCLUDED.owner_label,
                relationship = EXCLUDED.relationship,
                is_primary = EXCLUDED.is_primary,
                updated_at = NOW()
            """,
            (user_id, workspace_id, last4, owner, relationship, is_primary),
        )


def _settings_query_for_owner(conn, user_id: int, workspace_id: str | None = None) -> str:
    workspace_id = workspace_id or _workspace_id_for_user(conn, user_id)
    row = conn.execute(
        """
        INSERT INTO email_monitor_settings (user_id, workspace_id, gmail_query, auto_commit_confidence)
        VALUES (%s, %s, %s, 999)
        ON CONFLICT (workspace_id) DO UPDATE
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
        (user_id, workspace_id, DEFAULT_QUERY),
    ).fetchone()
    gmail_query = (row or {}).get("gmail_query") or DEFAULT_QUERY
    if "orden patronal" not in gmail_query.lower() and "noreply@ccss.sa.cr" not in gmail_query.lower():
        gmail_query = f'({gmail_query} OR from:noreply@ccss.sa.cr OR subject:"Generación de Orden Patronal Digital")'
        conn.execute(
            "UPDATE email_monitor_settings SET gmail_query = %s, updated_at = NOW() WHERE workspace_id = %s",
            (gmail_query, workspace_id),
        )
    return gmail_query


def _require_owner_user() -> dict[str, Any]:
    user = require_roles("owner")
    return user


def get_email_monitor_status() -> dict[str, Any]:
    user = _require_owner_user()
    user_id = int(user["id"])
    with get_connection() as conn:
        workspace_id = _workspace_id_for_user(conn, user_id)

    with get_connection() as conn:
        ensure_email_tables(conn)
        _seed_default_card_aliases(conn, user_id, workspace_id)
        settings = conn.execute(
            """
            INSERT INTO email_monitor_settings (user_id, workspace_id, gmail_query)
            VALUES (%s, %s, %s)
            ON CONFLICT (workspace_id)
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
            (user_id, workspace_id, DEFAULT_QUERY),
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
            WHERE workspace_id = %s
            """,
            (workspace_id,),
        ).fetchone()
        ignored = conn.execute(
            """
            SELECT COUNT(*) AS ignored
            FROM email_ingested_messages
            WHERE workspace_id = %s AND status = 'ignored'
            """,
            (workspace_id,),
        ).fetchone()
        totals = dict(totals)
        totals["ignored"] = int((ignored or {}).get("ignored") or 0)
        conn.commit()

    gmail_ready = all(
        os.getenv(key)
        for key in ["GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"]
    )
    gmail_push_ready = gmail_ready and all(
        os.getenv(key)
        for key in ["GMAIL_PUBSUB_TOPIC", "GMAIL_PUBSUB_VERIFICATION_TOKEN", "EMAIL_MONITOR_CRON_SECRET"]
    )

    return {
        "status": "OK",
        "owner_only": True,
        "gmail_ready": gmail_ready,
        "gmail_push_ready": gmail_push_ready,
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
            "GMAIL_PUBSUB_TOPIC",
            "GMAIL_PUBSUB_VERIFICATION_TOKEN",
            "EMAIL_MONITOR_CRON_SECRET",
        ],
    }


def _auto_apply_receivable_payment_from_candidate(conn, user_id: int, transaction_id: int, candidate: dict[str, Any]) -> None:
    workspace_id = _workspace_id_for_user(conn, user_id)
    """When an accepted email is an income from Emily/Sidey, reduce IOU balance.

    This keeps Cuentas por cobrar in sync immediately after the user confirms a
    SINPE Móvil payment instead of waiting for a later refresh job.
    """
    if candidate.get("transaction_type") not in {"income", "reimbursement"}:
        return
    text = " ".join([
        str(candidate.get("description") or ""),
        str(candidate.get("category") or ""),
        str(candidate.get("account") or ""),
        str(candidate.get("notes") or ""),
    ]).lower()
    payer = "Emily" if "emily" in text else "Sidey" if "sidey" in text else None
    if not payer:
        return
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receivables (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL DEFAULT 1,
                person_name TEXT NOT NULL,
                original_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                pending_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                notes TEXT,
                source_type TEXT NOT NULL DEFAULT 'manual',
                source_key TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receivable_payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL DEFAULT 1,
                receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
                amount NUMERIC(14,2) NOT NULL,
                source_transaction_id BIGINT,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        rec = conn.execute(
            """
            SELECT id, original_amount, paid_amount, pending_amount
            FROM receivables
            WHERE workspace_id = %s
              AND LOWER(TRIM(person_name)) = LOWER(TRIM(%s))
              AND source_type = 'additional_card_auto'
            ORDER BY id ASC
            LIMIT 1
            """,
            (workspace_id, payer),
        ).fetchone()
        if not rec:
            return
        already = conn.execute(
            """
            SELECT id FROM receivable_payments
            WHERE workspace_id = %s AND source_transaction_id = %s
            LIMIT 1
            """,
            (workspace_id, transaction_id),
        ).fetchone()
        if already:
            return
        pending = float(rec.get("pending_amount") or 0)
        amount = min(float(candidate.get("amount") or 0), max(pending, 0))
        if amount <= 0:
            return
        new_paid = float(rec.get("paid_amount") or 0) + amount
        new_pending = max(float(rec.get("original_amount") or 0) - new_paid, 0)
        status = "completed" if new_pending <= 0.01 else "partial"
        conn.execute(
            """
            INSERT INTO receivable_payments (user_id, workspace_id, receivable_id, amount, source_transaction_id, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, workspace_id, rec["id"], amount, transaction_id, f"Pago detectado automáticamente desde correo: {candidate.get('description') or ''}"),
        )
        conn.execute(
            """
            UPDATE receivables
            SET paid_amount = %s, pending_amount = %s, status = %s, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            """,
            (new_paid, new_pending, status, rec["id"], workspace_id),
        )
    except Exception:
        # Never block saving the financial transaction because IOU sync failed.
        return


def _insert_transaction(conn, user_id: int, candidate: dict[str, Any]) -> int:
    if candidate.get("transaction_type") in {"statement", "ignored", "internal_transfer"}:
        raise ValueError("Los estados de cuenta, correos ignorados o movimientos internos no se guardan como transacciones directas.")
    category = normalize_category(candidate["category"], candidate["transaction_type"])
    row = conn.execute(
        """
        INSERT INTO transactions (
            user_id,
            workspace_id,
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (
            user_id,
            _workspace_id_for_user(conn, user_id),
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
    transaction_id = int(row["id"])
    _auto_apply_receivable_payment_from_candidate(conn, user_id, transaction_id, candidate)
    return transaction_id


def _extract_card_last4_from_account(account: str | None) -> str | None:
    match = re.search(r"(\d{4})", account or "")
    return match.group(1) if match else None


def _enrich_candidate_with_card_alias(conn, workspace_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
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
        WHERE workspace_id = %s AND card_last4 = %s
        LIMIT 1
        """,
        (workspace_id, last4),
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


def _transaction_duplicate_match(conn, workspace_id: str, candidate: dict[str, Any]) -> int | None:
    """Return an existing saved transaction id for exact duplicates."""
    row = conn.execute(
        """
        SELECT id
        FROM transactions
        WHERE workspace_id = %s
        AND transaction_date = %s
        AND ABS(amount - %s) < 0.01
        AND transaction_type = %s
        AND LOWER(description) = LOWER(%s)
        LIMIT 1
        """,
        (
            workspace_id,
            candidate["transaction_date"],
            candidate["amount"],
            candidate["transaction_type"],
            candidate["description"],
        ),
    ).fetchone()
    return int(row["id"]) if row else None


def _existing_receivable_payment_match(conn, workspace_id: str, candidate: dict[str, Any]) -> int | None:
    """Prefer an already-recorded Sidey receivable payment over a new email income."""
    if candidate.get("transaction_type") not in {"income", "reimbursement"}:
        return None
    text = " ".join(str(candidate.get(key) or "") for key in ("description", "notes", "account")).lower()
    if "sidey" not in text:
        return None
    tables = conn.execute(
        "SELECT to_regclass('public.receivables') IS NOT NULL AS r, to_regclass('public.receivable_payments') IS NOT NULL AS p"
    ).fetchone()
    if not tables or not tables["r"] or not tables["p"]:
        return None
    row = conn.execute(
        """
        SELECT t.id
        FROM transactions t
        LEFT JOIN receivable_payments rp
          ON rp.workspace_id = t.workspace_id
         AND rp.source_transaction_id = t.id
        LEFT JOIN receivables r
          ON r.workspace_id = t.workspace_id
         AND r.id = rp.receivable_id
        WHERE t.workspace_id = %s
          AND t.transaction_date::date = %s::date
          AND ABS(t.amount - %s) < 0.01
          AND t.transaction_type = 'income'
          AND (
              LOWER(COALESCE(r.person_name, '')) = 'sidey'
              OR t.source = 'receivable_manual'
          )
        ORDER BY CASE WHEN LOWER(COALESCE(r.person_name, '')) = 'sidey' THEN 0 ELSE 1 END, t.id
        LIMIT 1
        """,
        (workspace_id, candidate["transaction_date"], candidate["amount"]),
    ).fetchone()
    return int(row["id"]) if row else None


def _candidate_duplicate_match(conn, workspace_id: str, candidate: dict[str, Any], current_fingerprint: str | None = None):
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
            WHERE workspace_id = %s
              AND dedupe_key = %s
              AND (%s IS NULL OR fingerprint <> %s)
              AND status IN ('pending','confirmed','auto_saved')
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (workspace_id, dedupe_key, current_fingerprint, current_fingerprint),
        ).fetchone()
        if row:
            return row

    return find_semantic_duplicate(conn, workspace_id, candidate, current_fingerprint)




def _repair_orphan_duplicate_links(conn, workspace_id: str) -> int:
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
              ON canonical_row.workspace_id = duplicate_row.workspace_id
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
            WHERE duplicate_row.workspace_id = %s
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
        (workspace_id,),
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

def _find_existing_ingested(conn, workspace_id: str, email_fp: str, provider_message_id: str | None):
    if provider_message_id:
        row = conn.execute(
            """
            SELECT id
            FROM email_ingested_messages
            WHERE workspace_id = %s
              AND provider = 'gmail'
              AND provider_message_id = %s
            LIMIT 1
            """,
            (workspace_id, provider_message_id),
        ).fetchone()
        if row:
            return row
    return conn.execute(
        """
        SELECT id
        FROM email_ingested_messages
        WHERE workspace_id = %s
          AND fingerprint = %s
        LIMIT 1
        """,
        (workspace_id, email_fp),
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
    workspace_id = _workspace_id_for_user(conn, user_id)
    raw_excerpt = (body or reason or "")[:1200]
    raw_body = (body or "")[:20000]
    existing = _find_existing_ingested(conn, workspace_id, email_fp, provider_message_id)
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
            WHERE id = %s AND workspace_id = %s
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
                workspace_id,
            ),
        )
        return email_id

    row = conn.execute(
        """
        INSERT INTO email_ingested_messages (
            user_id, workspace_id, provider, provider_message_id, fingerprint, sender, subject,
            received_at, bank, status, raw_excerpt, raw_body, body_text,
            attachment_names, attachment_count, parse_reason
        )
        VALUES (%s, %s, 'gmail', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (workspace_id, provider, provider_message_id)
        WHERE provider_message_id IS NOT NULL
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
            workspace_id,
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
    attachment_text: str | None = None,
) -> dict[str, Any]:
    if user_id is None:
        _require_owner_user()
        user_id = get_current_user_id()

    attachment_names = attachment_names or []
    email_fp = fingerprint_email(sender, subject, body, received_at)
    payroll_report = parse_ccss_order_patronal(subject, sender, attachment_text or body)

    if payroll_report:
        with get_connection() as conn:
            ensure_email_tables(conn)
            workspace_id = _workspace_id_for_user(conn, user_id)
            email_message_id = _upsert_ingested_message(
                conn, user_id=user_id, provider_message_id=provider_message_id,
                email_fp=email_fp, sender=sender, subject=subject, received_at=received_at,
                bank="ccss", status="payroll_statement", body=body,
                reason=f"Orden patronal CCSS {payroll_report['period_month']} procesada.",
                attachment_names=attachment_names,
            )
            row = conn.execute(
                """
                INSERT INTO payroll_salary_reports (
                    user_id, workspace_id, email_message_id, provider_message_id,
                    period_month, reported_salary, trans_previous_salary,
                    previous_salary, daily_subsidy, employer_number, verification_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id, period_month)
                DO UPDATE SET email_message_id = EXCLUDED.email_message_id,
                    provider_message_id = EXCLUDED.provider_message_id,
                    reported_salary = EXCLUDED.reported_salary,
                    trans_previous_salary = EXCLUDED.trans_previous_salary,
                    previous_salary = EXCLUDED.previous_salary,
                    daily_subsidy = EXCLUDED.daily_subsidy,
                    employer_number = EXCLUDED.employer_number,
                    verification_code = EXCLUDED.verification_code,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    user_id, workspace_id, email_message_id, provider_message_id,
                    payroll_report["period_month"], payroll_report["reported_salary"],
                    payroll_report["trans_previous_salary"], payroll_report["previous_salary"],
                    payroll_report["daily_subsidy"], payroll_report.get("employer_number"),
                    payroll_report.get("verification_code"),
                ),
            ).fetchone()
            _log_email_event(
                conn, user_id=user_id, email_message_id=email_message_id,
                provider_message_id=provider_message_id, sender=sender, subject=subject,
                bank="ccss", action="payroll_statement", result="processed",
                extracted_payload=payroll_report,
                reason="Salario bruto oficial guardado desde Orden Patronal CCSS.",
            )
            conn.commit()
        return {
            "status": "PAYROLL_STATEMENT",
            "message": f"Orden patronal {payroll_report['period_month']} guardada.",
            "payroll_report_id": int(row["id"]),
            "payroll_report": payroll_report,
            "candidate": None,
        }

    parsed = parse_financial_email(subject, sender, body, received_at)
    parsed["attachment_names"] = attachment_names

    with get_connection() as conn:
        ensure_email_tables(conn)
        workspace_id = _workspace_id_for_user(conn, user_id)
        parsed = apply_workspace_email_rules(conn, workspace_id, parsed)
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
            removed_mirrors = _delete_pending_internal_mirrors(conn, workspace_id, parsed) if _candidate_is_internal(parsed) else 0
            conn.commit()
            return {
                "status": "IGNORED_EMAIL",
                "message": parsed.get("ignore_reason") or "Correo ignorado.",
                "ignored": True,
                "candidate": None,
                "removed_internal_mirrors": removed_mirrors if 'removed_mirrors' in locals() else 0,
            }

        if parsed.get("email_kind") == "statement":
            # Store the PDF extraction separately from the email HTML. The PDF
            # is appended after the body during Gmail parsing, so clipping the
            # combined body previously preserved CSS instead of transactions.
            statement_text = (attachment_text or "").strip() or (body or "").strip()
            statement_row = conn.execute(
                """
                INSERT INTO email_statement_documents (
                    user_id, workspace_id, email_message_id, bank, subject, statement_month,
                    received_at, attachment_names, extracted_text_excerpt, extracted_text, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending_reconciliation')
                ON CONFLICT (workspace_id, email_message_id)
                DO UPDATE SET
                    bank = EXCLUDED.bank,
                    subject = EXCLUDED.subject,
                    statement_month = EXCLUDED.statement_month,
                    received_at = COALESCE(EXCLUDED.received_at, email_statement_documents.received_at),
                    attachment_names = EXCLUDED.attachment_names,
                    extracted_text_excerpt = EXCLUDED.extracted_text_excerpt,
                    extracted_text = EXCLUDED.extracted_text,
                    status = 'pending_reconciliation',
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    user_id,
                    workspace_id,
                    email_message_id,
                    parsed["bank"],
                    subject,
                    parsed.get("statement_month"),
                    received_at,
                    attachment_names,
                    statement_text[:2500],
                    statement_text,
                ),
            ).fetchone()
            reconciliation = None
            if parsed.get("bank") in {"multimoney", "bac"} and statement_row:
                try:
                    reconciliation = reconcile_statement(
                        conn,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        statement_id=int(statement_row["id"]),
                    )
                except HTTPException as exc:
                    if parsed.get("bank") != "bac" or exc.status_code != 422:
                        raise
                    # BAC publishes more than one PDF layout. Keep an unknown
                    # layout pending for inspection instead of failing the Gmail
                    # scan or, worse, importing unsigned/guessed movements.
                    reconciliation = {
                        "status": "PENDING_LAYOUT",
                        "statement_id": int(statement_row["id"]),
                        "message": str(exc.detail),
                    }
            # Remove old zero-amount statement candidates if this message had any.
            conn.execute(
                """
                DELETE FROM email_transaction_candidates
                WHERE workspace_id = %s
                  AND email_message_id = %s
                  AND transaction_type = 'statement'
                """,
                (workspace_id, email_message_id),
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
                "reconciliation": reconciliation,
            }

        parsed = _enrich_candidate_with_card_alias(conn, workspace_id, parsed)

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

        if _internal_mirror_exists(conn, workspace_id, parsed):
            removed_mirrors = _delete_pending_internal_mirrors(conn, workspace_id, parsed)
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
                reason="Movimiento espejo de una transferencia interna ya detectada; no se genera candidato financiero.",
            )
            conn.execute(
                """
                UPDATE email_ingested_messages
                SET status = 'ignored', parse_reason = %s
                WHERE id = %s AND workspace_id = %s
                """,
                ("Movimiento espejo de transferencia interna ya detectada.", email_message_id, workspace_id),
            )
            conn.commit()
            return {
                "status": "IGNORED_EMAIL",
                "message": "Movimiento espejo de transferencia interna ya detectada.",
                "ignored": True,
                "candidate": None,
                "removed_internal_mirrors": removed_mirrors,
            }

        scheduled_match = _scheduled_commitment_match(conn, workspace_id, parsed)
        duplicate_candidate = _candidate_duplicate_match(conn, workspace_id, parsed, candidate_fp)
        replace_existing_duplicate = False
        existing_transaction_id = (
            _existing_receivable_payment_match(conn, workspace_id, parsed)
            or _transaction_duplicate_match(conn, workspace_id, parsed)
        )
        if scheduled_match:
            transaction_id, review_reason = scheduled_match
            candidate_status = "duplicate"
            duplicate_of = None
        elif existing_transaction_id:
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
                user_id, workspace_id, email_message_id, fingerprint, transaction_id,
                transaction_date, description, amount, transaction_type,
                category, account, source, notes, original_amount, original_currency,
                exchange_rate, card_last4, card_owner, billing_cycle_start,
                billing_cycle_end, dedupe_key, duplicate_of, canonical_transaction_id,
                transaction_time, raw_description, normalized_description, confidence,
                auto_commit_allowed, personal_rule_id, status, review_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, fingerprint)
            WHERE fingerprint IS NOT NULL
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
                auto_commit_allowed = EXCLUDED.auto_commit_allowed,
                personal_rule_id = EXCLUDED.personal_rule_id,
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
                workspace_id,
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
                bool(parsed.get("auto_commit_allowed")),
                parsed.get("personal_rule_id"),
                candidate_status,
                review_reason,
            ),
        ).fetchone()
        candidate_row = dict(candidate_row) if candidate_row else {}

        # A combined scheduled commitment (for example Casa + préstamo papá)
        # may not have one canonical transaction because part of it is supplied
        # by the fixed-expense calendar. Keep a self trace so the duplicate is
        # auditable without inventing a second financial transaction.
        if scheduled_match and candidate_status == "duplicate" and not transaction_id:
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET canonical_transaction_id = id, updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (int(candidate_row["id"]), workspace_id),
            )
            candidate_row["canonical_transaction_id"] = candidate_row["id"]

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
                WHERE id = %s AND workspace_id = %s
                  AND status = 'duplicate'
                """,
                (int(canonical_candidate_id), int(canonical_candidate_id), int(candidate_row["id"]), workspace_id),
            )
            candidate_row["duplicate_of"] = int(canonical_candidate_id)
            candidate_row["canonical_transaction_id"] = int(canonical_candidate_id)

        if candidate_status != "duplicate" and candidate_row and not candidate_row.get("canonical_transaction_id"):
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET canonical_transaction_id = id, updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (int(candidate_row["id"]), workspace_id),
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
                WHERE id = %s AND workspace_id = %s
                """,
                (int(candidate_row["id"]), int(candidate_row["id"]), int(duplicate_candidate["id"]), workspace_id),
            )

        # Backfill histórico y defensa adicional para corridas reentrantes.
        _repair_orphan_duplicate_links(conn, workspace_id)
        refreshed_row = conn.execute(
            """
            SELECT *
            FROM email_transaction_candidates
            WHERE id = %s AND workspace_id = %s
            """,
            (int(candidate_row["id"]), workspace_id),
        ).fetchone()
        candidate_row = dict(refreshed_row) if refreshed_row else candidate_row
        _assert_duplicate_has_trace(candidate_row)

        if (
            auto_commit
            and candidate_row.get("status") == "pending"
            and bool(candidate_row.get("auto_commit_allowed"))
            and float(candidate_row.get("confidence") or 0) >= AUTO_COMMIT_CONFIDENCE
        ):
            transaction_id = _insert_transaction(conn, user_id, candidate_row)
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'auto_saved',
                    transaction_id = %s,
                    canonical_transaction_id = COALESCE(canonical_transaction_id, id),
                    review_reason = 'Guardado automáticamente desde Gmail por alta confianza.',
                    updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                  AND status = 'pending'
                """,
                (transaction_id, int(candidate_row["id"]), workspace_id),
            )
            candidate_row["status"] = "auto_saved"
            candidate_row["transaction_id"] = transaction_id
            candidate_row["canonical_transaction_id"] = candidate_row.get("canonical_transaction_id") or candidate_row["id"]
            candidate_status = "auto_saved"
            review_reason = "Guardado automáticamente desde Gmail por alta confianza."

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

def list_email_candidates(status_filter: str | None = None, limit: int = 250) -> dict[str, Any]:
    _require_owner_user()
    user_id = get_current_user_id()
    with get_connection() as conn:
        workspace_id = _workspace_id_for_user(conn, user_id)

    safe_limit = max(1, min(int(limit or 250), 500))
    where = "WHERE c.workspace_id = %s"
    params: list[Any] = [workspace_id]
    if status_filter:
        where += " AND c.status = %s"
        params.append(status_filter)

    params.append(safe_limit)

    with get_connection() as conn:
        ensure_email_tables(conn)
        _seed_default_card_aliases(conn, user_id, workspace_id)
        rows = conn.execute(
            f"""
            SELECT
                c.*,
                m.sender AS email_sender,
                m.subject AS email_subject,
                m.received_at AS email_received_at,
                m.status AS email_status
            FROM email_transaction_candidates c
            LEFT JOIN email_ingested_messages m ON m.id = c.email_message_id
            {where}
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                COUNT(*) FILTER (WHERE status = 'duplicate') AS duplicate,
                COUNT(*) FILTER (WHERE status = 'confirmed') AS confirmed,
                COUNT(*) FILTER (WHERE status = 'auto_saved') AS auto_saved,
                COUNT(*) FILTER (WHERE status = 'rejected') AS rejected
            FROM email_transaction_candidates
            WHERE workspace_id = %s
            """,
            (workspace_id,),
        ).fetchone()
        conn.commit()

    return {
        "status": "OK",
        "items": [dict(row) for row in rows],
        "totals": dict(totals or {}),
        "limit": safe_limit,
    }


def decide_candidate(candidate_id: int, decision: str) -> dict[str, Any]:
    _require_owner_user()
    user_id = get_current_user_id()
    with get_connection() as conn:
        workspace_id = _workspace_id_for_user(conn, user_id)
    decision_clean = (decision or "").lower().strip()

    with get_connection() as conn:
        ensure_email_tables(conn)
        row = conn.execute(
            """
            SELECT *
            FROM email_transaction_candidates
            WHERE id = %s AND workspace_id = %s
            """,
            (candidate_id, workspace_id),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Candidato no encontrado.")

        candidate = dict(row)

        if decision_clean in {"reject", "rechazar", "rejected"}:
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'rejected', updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (candidate_id, workspace_id),
            )
            conn.commit()
            return {"status": "OK", "message": "Candidato rechazado."}

        if decision_clean not in {"confirm", "confirmar", "guardar", "save"}:
            raise HTTPException(status_code=400, detail="Decisión inválida.")

        if candidate.get("status") == "duplicate":
            return {
                "status": "OK",
                "message": "Es duplicado; no se agrega a finanzas para evitar repetir el movimiento.",
                "canonical_transaction_id": candidate.get("canonical_transaction_id") or candidate.get("duplicate_of"),
            }

        if candidate.get("transaction_id"):
            return {"status": "OK", "message": "Ya estaba guardado.", "transaction_id": candidate["transaction_id"]}

        if candidate.get("transaction_type") in {"statement", "internal_transfer"}:
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'confirmed', updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (candidate_id, workspace_id),
            )
            conn.commit()
            return {"status": "OK", "message": "Correo marcado como revisado; no afecta finanzas."}

        transaction_id = _insert_transaction(conn, user_id, candidate)
        conn.execute(
            """
            UPDATE email_transaction_candidates
            SET status = 'confirmed', transaction_id = %s, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            """,
            (transaction_id, candidate_id, workspace_id),
        )
        conn.commit()

    return {"status": "OK", "message": "Movimiento guardado.", "transaction_id": transaction_id}


def _learned_rule_signature(conn, workspace_id: str, candidate: dict[str, Any]) -> dict[str, str | None]:
    """Build a strict reusable signature; amount is deliberately not part of it."""
    direction = str(candidate.get("dedupe_key") or "").rsplit("|", 1)[-1].lower()
    if direction not in {"in", "out", "payment"}:
        direction = None
    notes = str(candidate.get("notes") or "")
    origin = re.search(r"origen:\s*([^|]+)", notes, re.I)
    destination = re.search(r"destino:\s*([^|]+)", notes, re.I)

    def account_key(match):
        digits = re.findall(r"\d{4}", match.group(1) if match else "")
        if not digits:
            return None
        row = conn.execute(
            """
            SELECT account_key FROM email_financial_accounts
            WHERE workspace_id = %s AND account_last4 = %s AND active = TRUE
            LIMIT 1
            """,
            (workspace_id, digits[-1]),
        ).fetchone()
        return str(row["account_key"]) if row else None

    return {
        "direction": direction,
        "origin_account_key": account_key(origin),
        "destination_account_key": account_key(destination),
        "concept": str(candidate.get("raw_description") or candidate.get("description") or "").strip(),
    }


def classify_candidate(
    candidate_id: int,
    description: str,
    transaction_type: str,
    category: str,
    remember_rule: bool = True,
    auto_commit_future: bool = True,
) -> dict[str, Any]:
    """Save a reviewed candidate and optionally learn an exact, account-bound rule."""
    _require_owner_user()
    user_id = get_current_user_id()
    clean_description = re.sub(r"\s+", " ", description or "").strip()
    clean_type = (transaction_type or "").strip().lower()
    if not clean_description:
        raise HTTPException(status_code=400, detail="Decime qué fue este movimiento.")
    if clean_type not in {"expense", "income", "debt_payment"}:
        raise HTTPException(status_code=400, detail="Tipo de movimiento inválido.")
    clean_category = normalize_category(category, clean_type)

    with get_connection() as conn:
        workspace_id = _workspace_id_for_user(conn, user_id)
        ensure_email_tables(conn)
        row = conn.execute(
            "SELECT * FROM email_transaction_candidates WHERE id = %s AND workspace_id = %s",
            (candidate_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Candidato no encontrado.")
        candidate = dict(row)
        if candidate.get("transaction_id"):
            return {"status": "OK", "message": "Ya estaba guardado.", "transaction_id": candidate["transaction_id"]}
        if candidate.get("status") != "pending":
            raise HTTPException(status_code=409, detail="Este movimiento ya no está pendiente.")

        rule_id = None
        learned = False
        signature = _learned_rule_signature(conn, workspace_id, candidate)
        # Some BAC templates do not expose masked account numbers. Exact concept
        # + direction is still strict enough; account keys further constrain it
        # whenever the email supplies them.
        if remember_rule and signature["concept"] and signature["direction"]:
            digest = hashlib.sha256(
                "|".join(str(signature[key] or "") for key in ("direction", "origin_account_key", "destination_account_key", "concept")).encode()
            ).hexdigest()[:16]
            learned_row = conn.execute(
                """
                INSERT INTO email_classification_rules (
                    user_id, workspace_id, name, priority, concept_pattern, match_mode,
                    direction, origin_account_key, destination_account_key, action,
                    output_description, transaction_type, category, allow_auto_commit,
                    review_reason, metadata, active, updated_at
                ) VALUES (%s, %s, %s, 200, %s, 'exact', %s, %s, %s, 'classify', %s, %s, %s, %s,
                          %s, %s::jsonb, TRUE, NOW())
                ON CONFLICT (workspace_id, name) DO UPDATE SET
                    output_description = EXCLUDED.output_description,
                    transaction_type = EXCLUDED.transaction_type,
                    category = EXCLUDED.category,
                    allow_auto_commit = EXCLUDED.allow_auto_commit,
                    review_reason = EXCLUDED.review_reason,
                    metadata = EXCLUDED.metadata,
                    active = TRUE,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    user_id, workspace_id, f"learned_email_{digest}", signature["concept"],
                    signature["direction"], signature["origin_account_key"], signature["destination_account_key"],
                    clean_description, clean_type, clean_category, bool(auto_commit_future),
                    "Clasificación enseñada por Kenneth desde la revisión de correos.",
                    json.dumps({"learned_from_candidate_id": candidate_id, "strict_signature": True}),
                ),
            ).fetchone()
            rule_id = int(learned_row["id"])
            learned = True

        candidate.update(description=clean_description, transaction_type=clean_type, category=clean_category)
        transaction_id = _insert_transaction(conn, user_id, candidate)
        conn.execute(
            """
            UPDATE email_transaction_candidates
            SET description = %s, transaction_type = %s, category = %s,
                transaction_id = %s, status = 'confirmed', personal_rule_id = %s,
                auto_commit_allowed = %s,
                review_reason = %s, updated_at = NOW()
            WHERE id = %s AND workspace_id = %s
            """,
            (
                clean_description, clean_type, clean_category, transaction_id, rule_id,
                bool(learned and auto_commit_future),
                "Clasificado manualmente y regla personal aprendida." if learned else "Clasificado manualmente.",
                candidate_id, workspace_id,
            ),
        )
        conn.commit()

    message = "Guardado y aprendido. La próxima coincidencia exacta será automática." if learned and auto_commit_future else "Movimiento guardado."
    if remember_rule and not learned:
        message += " No aprendí una automatización porque faltó identificar con seguridad las cuentas o la dirección."
    return {"status": "OK", "message": message, "transaction_id": transaction_id, "personal_rule_id": rule_id, "learned": learned}


def bulk_decide_candidates(candidate_ids: list[int], decision: str) -> dict[str, Any]:
    """Confirm or reject several review candidates.

    Confirming is the exact moment where email data becomes real finance data.
    Duplicates are intentionally skipped because their canonical movement is the
    one that must be accepted into transactions. This keeps Gmail scans
    idempotent: repeated scans do not create repeated finance movements.
    """
    _require_owner_user()
    user_id = get_current_user_id()
    with get_connection() as conn:
        workspace_id = _workspace_id_for_user(conn, user_id)
    decision_clean = (decision or "").lower().strip()
    if decision_clean not in {"confirm", "confirmar", "guardar", "save", "reject", "rechazar", "rejected"}:
        raise HTTPException(status_code=400, detail="Decisión inválida.")

    unique_ids = []
    seen = set()
    for value in candidate_ids or []:
        try:
            cid = int(value)
        except Exception:
            continue
        if cid > 0 and cid not in seen:
            unique_ids.append(cid)
            seen.add(cid)

    if not unique_ids:
        return {"status": "OK", "message": "No había movimientos seleccionados.", "confirmed": 0, "rejected": 0, "skipped": 0, "items": []}

    confirmed = rejected = skipped = 0
    items: list[dict[str, Any]] = []

    with get_connection() as conn:
        ensure_email_tables(conn)
        placeholders = ",".join(["%s"] * len(unique_ids))
        rows = conn.execute(
            f"""
            SELECT *
            FROM email_transaction_candidates
            WHERE workspace_id = %s AND id IN ({placeholders})
            ORDER BY created_at ASC, id ASC
            """,
            tuple([workspace_id] + unique_ids),
        ).fetchall()

        by_id = {int(row["id"]): dict(row) for row in rows}
        for cid in unique_ids:
            candidate = by_id.get(cid)
            if not candidate:
                skipped += 1
                items.append({"id": cid, "status": "skipped", "message": "No encontrado."})
                continue

            if decision_clean in {"reject", "rechazar", "rejected"}:
                if candidate.get("status") in {"confirmed", "auto_saved"}:
                    skipped += 1
                    items.append({"id": cid, "status": "skipped", "message": "Ya estaba guardado en finanzas."})
                    continue
                conn.execute(
                    """
                    UPDATE email_transaction_candidates
                    SET status = 'rejected', updated_at = NOW()
                    WHERE id = %s AND workspace_id = %s
                    """,
                    (cid, workspace_id),
                )
                rejected += 1
                items.append({"id": cid, "status": "rejected"})
                continue

            if candidate.get("status") == "duplicate":
                skipped += 1
                items.append({"id": cid, "status": "skipped", "message": "Duplicado: se guarda el canónico, no este registro."})
                continue

            if candidate.get("transaction_id"):
                skipped += 1
                items.append({"id": cid, "status": "skipped", "message": "Ya estaba guardado.", "transaction_id": candidate.get("transaction_id")})
                continue

            if candidate.get("transaction_type") in {"statement", "ignored", "internal_transfer"}:
                skipped += 1
                items.append({"id": cid, "status": "skipped", "message": "No es movimiento financiero directo."})
                continue

            transaction_id = _insert_transaction(conn, user_id, candidate)
            conn.execute(
                """
                UPDATE email_transaction_candidates
                SET status = 'confirmed', transaction_id = %s, updated_at = NOW()
                WHERE id = %s AND workspace_id = %s
                """,
                (transaction_id, cid, workspace_id),
            )
            confirmed += 1
            items.append({"id": cid, "status": "confirmed", "transaction_id": transaction_id})

        conn.commit()

    return {
        "status": "OK",
        "message": f"Confirmados: {confirmed}. Rechazados: {rejected}. Omitidos: {skipped}.",
        "confirmed": confirmed,
        "rejected": rejected,
        "skipped": skipped,
        "items": items,
    }


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


def _process_gmail_message(service, *, message_id: str, owner_id: int, auto_commit: bool = False) -> dict[str, Any]:
    """Fetch and ingest one Gmail message through the existing parser pipeline."""
    full = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in full.get("payload", {}).get("headers", [])
    }
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
            attachment_text=pdf_text,
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

    return {
        "gmail_id": message_id,
        "subject": subject,
        "sender": sender,
        "status": result.get("status"),
        "message": result.get("message"),
        "candidate_status": (result.get("candidate") or {}).get("status"),
    }


def sync_gmail_for_owner(max_results: int = 100, auto_commit: bool = True, query: str | None = None, current_month_only: bool = True) -> dict[str, Any]:
    # Gmail/PubSub ingestion is automatic for high-confidence candidates.
    auto_commit = True
    service = _gmail_service()

    with get_connection() as conn:
        ensure_email_tables(conn)
        owner_id = _owner_user_id(conn)
        if not owner_id:
            raise RuntimeError("No encontré usuario owner para guardar correos.")
        owner_workspace_id = _workspace_id_for_user(conn, owner_id)
        _seed_default_card_aliases(conn, owner_id)
        settings_query = _settings_query_for_owner(conn, owner_id)
        conn.commit()

    # Do not let the UI's old max_results=25 starve the scanner. Current-month
    # financial inboxes can easily have more than 25 BAC/SINPE/MultiMoney emails.
    effective_max_results = max(int(max_results or 0), 150)
    base_query = (query or settings_query or DEFAULT_QUERY).strip()
    gmail_query = build_current_month_gmail_query(base_query) if current_month_only else base_query

    messages = _list_gmail_messages(service, gmail_query=gmail_query, max_results=effective_max_results)
    today = date.today()
    aguinaldo_start = date(today.year if today.month == 12 else today.year - 1, 12, 1)
    payroll_query = (
        'from:noreply@ccss.sa.cr subject:"Generación de Orden Patronal Digital" '
        f'after:{aguinaldo_start:%Y/%m/%d} -in:spam -in:trash'
    )
    payroll_messages = _list_gmail_messages(service, gmail_query=payroll_query, max_results=20)
    seen_ids = {item.get("id") for item in messages}
    messages.extend(item for item in payroll_messages if item.get("id") not in seen_ids)
    processed: list[dict[str, Any]] = []

    for item in messages:
        message_id = item.get("id")
        if not message_id:
            continue
        processed.append(
            _process_gmail_message(
                service,
                message_id=message_id,
                owner_id=owner_id,
                auto_commit=auto_commit,
            )
        )

    with get_connection() as conn:
        ensure_email_tables(conn)
        _repair_historical_cross_bank_mirrors(conn, owner_workspace_id)
        _repair_historical_scheduled_commitments(conn, owner_workspace_id)
        stored_statement_rows = conn.execute(
            """
            SELECT id, bank
            FROM email_statement_documents
            WHERE workspace_id = %s
              AND bank IN ('bac', 'multimoney')
              AND extracted_text IS NOT NULL
              AND LENGTH(TRIM(extracted_text)) > 0
              AND status IN ('pending_reconciliation', 'needs_review')
            ORDER BY received_at, id
            """,
            (owner_workspace_id,),
        ).fetchall()
        stored_reconciliations: list[dict[str, Any]] = []
        for statement in stored_statement_rows:
            try:
                result = reconcile_statement(
                    conn,
                    user_id=owner_id,
                    workspace_id=owner_workspace_id,
                    statement_id=int(statement["id"]),
                )
                stored_reconciliations.append(result)
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
                stored_reconciliations.append({
                    "status": "PENDING_LAYOUT",
                    "statement_id": int(statement["id"]),
                    "bank": statement["bank"],
                    "message": str(exc.detail),
                })
        conn.execute(
            """
            UPDATE email_monitor_settings
            SET last_scan_at = NOW(),
                updated_at = NOW(),
                gmail_query = %s,
                auto_commit_confidence = %s
            WHERE workspace_id = %s
            """,
            (settings_query or DEFAULT_QUERY, AUTO_COMMIT_CONFIDENCE, owner_workspace_id),
        )
        gmail_ids = [item.get("gmail_id") for item in processed if item.get("gmail_id")]
        final_rows = conn.execute(
            """
            SELECT
                m.provider_message_id,
                m.status AS email_status,
                m.parse_reason,
                c.status AS candidate_status,
                c.transaction_id
            FROM email_ingested_messages m
            LEFT JOIN email_transaction_candidates c ON c.email_message_id = m.id
            WHERE m.workspace_id = %s
              AND m.provider_message_id = ANY(%s)
            """,
            (owner_workspace_id, gmail_ids),
        ).fetchall() if gmail_ids else []
        conn.commit()

    final_by_gmail_id = {str(row["provider_message_id"]): dict(row) for row in final_rows}
    for item in processed:
        final = final_by_gmail_id.get(str(item.get("gmail_id") or ""))
        if not final:
            continue
        candidate_status = final.get("candidate_status")
        email_status = final.get("email_status")
        item["candidate_status"] = candidate_status
        if candidate_status in {"confirmed", "auto_saved"}:
            item["status"] = "OK"
            item["message"] = "Ya estaba en finanzas."
        elif candidate_status == "pending":
            item["status"] = "OK"
            item["message"] = "Pendiente de revisión."
        elif candidate_status == "duplicate":
            item["status"] = "DUPLICATE_EMAIL"
            item["message"] = "Movimiento duplicado; no se vuelve a guardar."
        elif email_status == "ignored":
            item["status"] = "IGNORED_EMAIL"
            item["message"] = final.get("parse_reason") or "Correo ignorado."
        elif email_status == "statement":
            item["status"] = "STATEMENT_DOCUMENT"
            item["message"] = final.get("parse_reason") or "Estado de cuenta para conciliación."

    auto_saved = sum(1 for item in processed if item.get("candidate_status") == "auto_saved")
    confirmed = sum(1 for item in processed if item.get("candidate_status") == "confirmed")
    pending = sum(1 for item in processed if item.get("candidate_status") == "pending")
    statements = sum(1 for item in processed if item.get("status") == "STATEMENT_DOCUMENT")
    payroll_statements = sum(1 for item in processed if item.get("status") == "PAYROLL_STATEMENT")
    ignored = sum(1 for item in processed if item.get("status") in {"IGNORED_EMAIL", "DUPLICATE_IGNORED_EMAIL"})
    duplicates = sum(1 for item in processed if item.get("status") == "DUPLICATE_EMAIL" or item.get("candidate_status") == "duplicate")
    errors = sum(1 for item in processed if item.get("status") == "ERROR")

    return {
        "status": "OK",
        "query": gmail_query,
        "found": len(messages),
        "processed": processed,
        "summary": {
            "auto_saved": auto_saved,
            "confirmed": confirmed,
            "pending": pending,
            "statements": statements,
            "payroll_statements": payroll_statements,
            "duplicates": duplicates,
            "ignored": ignored,
            "errors": errors,
            "stored_statements_reconciled": sum(
                1 for item in stored_reconciliations if item.get("status") == "OK"
            ),
        },
        "message": (
            f"Escaneo completado. Encontrados: {len(messages)}, pendientes: {pending}, "
            f"ya en finanzas: {confirmed + auto_saved}, estados: {statements}, "
            f"duplicados: {duplicates}, ignorados: {ignored}, errores: {errors}. "
            "Autoguardado limitado a reglas personales autorizadas."
        ),
    }


def cron_sync(secret: str | None, max_results: int = 20) -> dict[str, Any]:
    if not CRON_SECRET:
        raise HTTPException(status_code=503, detail="EMAIL_MONITOR_CRON_SECRET no está configurado.")
    if not secret or not hmac.compare_digest(secret, CRON_SECRET):
        raise HTTPException(status_code=403, detail="Cron secret inválido.")
    try:
        return sync_gmail_for_owner(max_results=max_results, auto_commit=True, current_month_only=True)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def renew_gmail_watch(secret: str | None) -> dict[str, Any]:
    """Create/renew Gmail push notifications (Gmail watches expire within 7 days)."""
    if not CRON_SECRET:
        raise HTTPException(status_code=503, detail="EMAIL_MONITOR_CRON_SECRET no está configurado.")
    if not secret or not hmac.compare_digest(secret, CRON_SECRET):
        raise HTTPException(status_code=403, detail="Cron secret inválido.")

    topic_name = os.getenv("GMAIL_PUBSUB_TOPIC", "").strip()
    if not topic_name:
        raise HTTPException(status_code=503, detail="GMAIL_PUBSUB_TOPIC no está configurado.")

    service = _gmail_service()
    response = service.users().watch(
        userId="me",
        body={"topicName": topic_name, "labelIds": ["INBOX"]},
    ).execute()
    history_id = str(response.get("historyId") or "")
    expiration_ms = int(response.get("expiration") or 0)
    expiration = (
        datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc)
        if expiration_ms
        else None
    )

    with get_connection() as conn:
        ensure_email_tables(conn)
        owner_id = _owner_user_id(conn)
        if not owner_id:
            raise RuntimeError("No encontré usuario owner para configurar Gmail watch.")
        workspace_id = _workspace_id_for_user(conn, owner_id)
        _settings_query_for_owner(conn, owner_id)
        conn.execute(
            """
            UPDATE email_monitor_settings
            SET gmail_history_id = %s,
                gmail_watch_expiration = %s,
                gmail_watch_topic = %s,
                updated_at = NOW()
            WHERE workspace_id = %s
            """,
            (history_id, expiration, topic_name, workspace_id),
        )
        conn.commit()

    return {
        "status": "OK",
        "history_id": history_id,
        "expiration": expiration.isoformat() if expiration else None,
        "message": "Gmail watch activado/renovado.",
    }


def process_gmail_push(payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    """Process a verified Google Pub/Sub Gmail notification idempotently."""
    expected_token = os.getenv("GMAIL_PUBSUB_VERIFICATION_TOKEN", "")
    if not expected_token:
        raise HTTPException(status_code=503, detail="GMAIL_PUBSUB_VERIFICATION_TOKEN no está configurado.")
    if not token or not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=403, detail="Token Pub/Sub inválido.")

    message = payload.get("message") or {}
    encoded_data = message.get("data")
    if not encoded_data:
        raise HTTPException(status_code=400, detail="Notificación Pub/Sub sin data.")
    try:
        padding = "=" * (-len(encoded_data) % 4)
        notification = json.loads(base64.urlsafe_b64decode(encoded_data + padding).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Data Pub/Sub inválida.") from exc

    pushed_history_id = str(notification.get("historyId") or "")
    email_address = str(notification.get("emailAddress") or "").lower()
    if not pushed_history_id:
        raise HTTPException(status_code=400, detail="Notificación Gmail sin historyId.")
    if email_address and email_address != OWNER_EMAIL.lower():
        raise HTTPException(status_code=403, detail="La notificación no pertenece al correo owner.")

    service = _gmail_service()
    with get_connection() as conn:
        ensure_email_tables(conn)
        owner_id = _owner_user_id(conn)
        if not owner_id:
            raise RuntimeError("No encontré usuario owner para procesar Gmail push.")
        workspace_id = _workspace_id_for_user(conn, owner_id)
        settings_query = _settings_query_for_owner(conn, owner_id)
        row = conn.execute(
            "SELECT gmail_history_id FROM email_monitor_settings WHERE workspace_id = %s",
            (workspace_id,),
        ).fetchone()
        previous_history_id = str((row or {}).get("gmail_history_id") or "")
        conn.commit()

    if not previous_history_id:
        # The first watch notification is only a checkpoint. A normal scan
        # catches anything that arrived before the watch was stored.
        result = sync_gmail_for_owner(max_results=150, current_month_only=True)
        processed = result.get("processed", [])
    else:
        message_ids: list[str] = []
        page_token: str | None = None
        try:
            while True:
                kwargs: dict[str, Any] = {
                    "userId": "me",
                    "startHistoryId": previous_history_id,
                    "historyTypes": ["messageAdded"],
                    "labelId": "INBOX",
                }
                if page_token:
                    kwargs["pageToken"] = page_token
                history = service.users().history().list(**kwargs).execute()
                for event in history.get("history", []) or []:
                    for added in event.get("messagesAdded", []) or []:
                        message_id = (added.get("message") or {}).get("id")
                        if message_id and message_id not in message_ids:
                            message_ids.append(message_id)
                page_token = history.get("nextPageToken")
                if not page_token:
                    break
            processed = [
                _process_gmail_message(
                    service,
                    message_id=message_id,
                    owner_id=owner_id,
                    auto_commit=True,
                )
                for message_id in message_ids
            ]
        except Exception as exc:
            # Gmail returns 404 when the stored historyId is too old. The
            # bounded cycle scan is the safe recovery path and remains idempotent.
            if getattr(exc, "status_code", None) != 404 and getattr(getattr(exc, "resp", None), "status", None) != 404:
                raise
            result = sync_gmail_for_owner(max_results=150, current_month_only=True)
            processed = result.get("processed", [])

    with get_connection() as conn:
        ensure_email_tables(conn)
        conn.execute(
            """
            UPDATE email_monitor_settings
            SET gmail_history_id = GREATEST(
                    COALESCE(NULLIF(gmail_history_id, '')::NUMERIC, 0),
                    %s::NUMERIC
                )::TEXT,
                last_scan_at = NOW(),
                updated_at = NOW(),
                gmail_query = %s
            WHERE workspace_id = %s
            """,
            (pushed_history_id, settings_query or DEFAULT_QUERY, workspace_id),
        )
        conn.commit()

    return {
        "status": "OK",
        "history_id": pushed_history_id,
        "processed_count": len(processed),
        "processed": processed,
    }
