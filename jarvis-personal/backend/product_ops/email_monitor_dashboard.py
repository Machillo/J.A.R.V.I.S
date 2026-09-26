from __future__ import annotations

from collections import defaultdict
from typing import Any


def _rate(value: int, total: int) -> float:
    return round(value * 100 / total, 2) if total else 0.0


def _rows(result) -> list[dict[str, Any]]:
    return [dict(row) for row in result.fetchall()]


def build_email_monitor_dashboard(conn) -> dict[str, Any]:
    """Owner-only operational view: aggregates by bank and parser, never by person.

    Google Workspace data may reach a human only aggregated and anonymized (Limited
    Use), so no row carries an account, an email, a message body or a financial value.
    """
    messages = _rows(conn.execute(
        """SELECT COALESCE(status,'unknown') AS status,COUNT(*) AS total
             FROM finva_email_messages
            WHERE created_at>=NOW()-INTERVAL '30 days'
            GROUP BY COALESCE(status,'unknown') ORDER BY total DESC"""
    ))
    candidates = _rows(conn.execute(
        """SELECT COALESCE(c.bank,'unknown') AS bank,
                  COALESCE(c.source_type,'unknown') AS source_type,
                  COALESCE(c.parser_name,'unknown') AS parser_name,
                  COALESCE(c.parser_version,'unknown') AS parser_version,
                  COALESCE(c.movement_kind,'unknown') AS movement_kind,
                  COUNT(*) FILTER (WHERE c.status='pending') AS pending,
                  COUNT(*) FILTER (WHERE c.status IN ('confirmed','rejected')) AS reviewed,
                  COUNT(*) FILTER (WHERE c.status='confirmed' AND cardinality(c.corrected_fields)=0) AS accepted,
                  COUNT(*) FILTER (WHERE c.status='confirmed' AND cardinality(c.corrected_fields)>0) AS corrected,
                  COUNT(*) FILTER (WHERE c.status='rejected') AS rejected,
                  MAX(c.updated_at) AS last_activity_at
             FROM finva_email_candidates c
            WHERE c.created_at>=NOW()-INTERVAL '90 days'
            GROUP BY c.bank,c.source_type,c.parser_name,c.parser_version,c.movement_kind
            ORDER BY last_activity_at DESC LIMIT 500"""
    ))
    connections = _rows(conn.execute(
        """SELECT COALESCE(status,'unknown') AS status,COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE last_error IS NOT NULL AND last_error<>'') AS with_error,
                  MAX(last_success_at) AS last_success_at,MAX(last_sync_at) AS last_sync_at
             FROM finva_gmail_connections GROUP BY COALESCE(status,'unknown') ORDER BY status"""
    ))
    statements = _rows(conn.execute(
        """SELECT COALESCE(bank,'unknown') AS bank,COALESCE(status,'unknown') AS status,
                  COALESCE(parser_name,'unknown') AS parser_name,
                  COALESCE(parser_version,'unknown') AS parser_version,
                  COUNT(*) AS total,COALESCE(SUM(movements_found),0) AS movements_found
             FROM finva_statement_documents
            WHERE created_at>=NOW()-INTERVAL '90 days'
            GROUP BY bank,status,parser_name,parser_version ORDER BY total DESC"""
    ))
    accounts = _rows(conn.execute(
        """SELECT COALESCE(ownership_status,'pending') AS ownership_status,COUNT(*) AS total
             FROM account_balances
            WHERE source='finva_email_discovery' AND is_active=TRUE
            GROUP BY COALESCE(ownership_status,'pending') ORDER BY ownership_status"""
    ))

    totals = defaultdict(int)
    for row in candidates:
        for key in ("pending", "reviewed", "accepted", "corrected", "rejected"):
            totals[key] += int(row.get(key) or 0)
    reviewed = totals["reviewed"]
    return {
        "periods": {"messages_days": 30, "candidates_days": 90, "statements_days": 90},
        "messages": messages,
        "connections": connections,
        "candidates": candidates,
        "statements": statements,
        "accounts": accounts,
        "totals": {
            **dict(totals),
            "acceptance_rate": _rate(totals["accepted"], reviewed),
            "correction_rate": _rate(totals["corrected"], reviewed),
            "rejection_rate": _rate(totals["rejected"], reviewed),
        },
        "privacy": "Operational metadata only; no message bodies, raw payloads, or financial amounts.",
    }
