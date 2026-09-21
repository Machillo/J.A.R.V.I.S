from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection


def _rate(value: int, total: int) -> float:
    return round((value / total) * 100, 2) if total else 0.0


def summarize_trust_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals = defaultdict(int)
    segments: list[dict[str, Any]] = []
    for row in rows:
        reviewed = int(row.get("reviewed") or 0)
        accepted = int(row.get("accepted_unchanged") or 0)
        corrected = int(row.get("corrected") or 0)
        rejected = int(row.get("rejected") or 0)
        pending = int(row.get("pending") or 0)
        for key, value in {
            "reviewed": reviewed,
            "accepted_unchanged": accepted,
            "corrected": corrected,
            "rejected": rejected,
            "pending": pending,
        }.items():
            totals[key] += value
        segments.append({
            "country": row.get("institution_country") or "unknown",
            "bank": row.get("bank") or "unknown",
            "source_type": row.get("source_type") or "unknown",
            "source_provider": row.get("source_provider") or "unknown",
            "parser_name": row.get("parser_name") or "unknown",
            "parser_version": row.get("parser_version") or "unknown",
            "reviewed": reviewed,
            "accepted_unchanged": accepted,
            "corrected": corrected,
            "rejected": rejected,
            "pending": pending,
            "acceptance_rate": _rate(accepted, reviewed),
            "correction_rate": _rate(corrected, reviewed),
            "rejection_rate": _rate(rejected, reviewed),
        })
    reviewed = totals["reviewed"]
    return {
        "totals": {
            **dict(totals),
            "acceptance_rate": _rate(totals["accepted_unchanged"], reviewed),
            "correction_rate": _rate(totals["corrected"], reviewed),
            "rejection_rate": _rate(totals["rejected"], reviewed),
        },
        "segments": segments,
        "definition": "Acceptance rate = accepted without changes / reviewed proposals",
    }


def get_gmail_trust_analytics() -> dict[str, Any]:
    account_id = get_current_account_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT institution_country,bank,source_type,source_provider,parser_name,parser_version,
                      COUNT(*) FILTER (WHERE status IN ('confirmed','rejected')) AS reviewed,
                      COUNT(*) FILTER (WHERE status='confirmed' AND cardinality(corrected_fields)=0) AS accepted_unchanged,
                      COUNT(*) FILTER (WHERE status='confirmed' AND cardinality(corrected_fields)>0) AS corrected,
                      COUNT(*) FILTER (WHERE status='rejected') AS rejected,
                      COUNT(*) FILTER (WHERE status='pending') AS pending
                 FROM finva_email_candidates
                WHERE account_id=%s AND workspace_id=%s
                GROUP BY institution_country,bank,source_type,source_provider,parser_name,parser_version
                ORDER BY reviewed DESC,bank,source_type,parser_name,parser_version""",
            (account_id, workspace_id),
        ).fetchall()
    return summarize_trust_rows([dict(row) for row in rows])
