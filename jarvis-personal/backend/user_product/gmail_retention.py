from __future__ import annotations

import os
from typing import Any

from backend.core.database import get_connection


def _days(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(1, min(value, 3650))


def retention_policy() -> dict[str, Any]:
    return {
        "review_evidence_days": _days("DINCR_GMAIL_REVIEW_EVIDENCE_DAYS", 30),
        "email_metadata_days": _days("DINCR_GMAIL_METADATA_DAYS", 90),
        "canonical_history": "until_account_deletion",
    }


def apply_gmail_retention() -> dict[str, int]:
    policy = retention_policy()
    with get_connection() as conn:
        evidence = conn.execute(
            """WITH changed AS (
                   UPDATE finva_email_candidates
                      SET raw_payload=NULL,updated_at=NOW()
                    WHERE raw_payload IS NOT NULL
                      AND reviewed_at IS NOT NULL
                      AND reviewed_at < NOW() - (%s * INTERVAL '1 day')
                    RETURNING id
               ) SELECT COUNT(*) AS total FROM changed""",
            (policy["review_evidence_days"],),
        ).fetchone()
        messages = conn.execute(
            """WITH changed AS (
                   UPDATE finva_email_messages m
                      SET sender=NULL,subject=NULL,parse_reason=NULL
                    WHERE (m.sender IS NOT NULL OR m.subject IS NOT NULL OR m.parse_reason IS NOT NULL)
                      AND COALESCE(m.received_at,m.created_at) < NOW() - (%s * INTERVAL '1 day')
                      AND NOT EXISTS (
                          SELECT 1 FROM finva_email_candidates c
                           WHERE c.email_message_id=m.id AND c.status='pending'
                      )
                    RETURNING m.id
               ) SELECT COUNT(*) AS total FROM changed""",
            (policy["email_metadata_days"],),
        ).fetchone()
        documents = conn.execute(
            """WITH changed AS (
                   UPDATE finva_statement_documents d
                      SET attachment_names=ARRAY[]::TEXT[],updated_at=NOW()
                    WHERE cardinality(d.attachment_names)>0
                      AND d.created_at < NOW() - (%s * INTERVAL '1 day')
                      AND NOT EXISTS (
                          SELECT 1 FROM finva_email_candidates c
                           WHERE c.statement_document_id=d.id AND c.status='pending'
                      )
                    RETURNING d.id
               ) SELECT COUNT(*) AS total FROM changed""",
            (policy["email_metadata_days"],),
        ).fetchone()
        conn.commit()
    return {
        "candidate_evidence_cleared": int((evidence or {}).get("total") or 0),
        "email_metadata_redacted": int((messages or {}).get("total") or 0),
        "attachment_names_redacted": int((documents or {}).get("total") or 0),
    }
