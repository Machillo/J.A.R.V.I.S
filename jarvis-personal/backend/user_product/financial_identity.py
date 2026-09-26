from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection


def _last4(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else ""


def _institution_label(code: str) -> str:
    labels = {"bac": "BAC", "popular": "Banco Popular", "multimoney": "MultiMoney"}
    return labels.get(code, code.replace("_", " ").title() or "Institución financiera")


def _account_signal(candidate: dict[str, Any]) -> dict[str, str] | None:
    direction = str(candidate.get("movement_direction") or "unknown")
    reference = (
        candidate.get("destination_account_reference")
        if direction == "in"
        else candidate.get("source_account_reference")
    )
    last4 = _last4(reference or candidate.get("source_account_label"))
    institution = str(candidate.get("bank") or "unknown").strip().lower()
    if not last4 or institution == "unknown":
        return None
    label = str(candidate.get("source_account_label") or "").strip()
    return {
        "institution_code": institution,
        "institution_name": _institution_label(institution),
        "institution_country": str(candidate.get("institution_country") or "CR").upper(),
        "account_last4": last4,
        "account_name": label or f"{_institution_label(institution)} •••• {last4}",
        "account_type": "credit_card" if candidate.get("movement_kind") == "card_purchase" or "tarjeta" in label.lower() else "checking",
        "currency": str(candidate.get("currency") or "CRC").upper(),
    }


def discover_candidate_account(
    conn,
    *,
    candidate_id: int,
    candidate: dict[str, Any],
    account_id: str,
    workspace_id: str,
    legacy_user_id: int | None = None,
) -> int | None:
    """Link a stable account signal without assuming that the account is owned.

    ``legacy_user_id`` is no longer written (ownership is the workspace); it stays
    in the signature until its callers stop passing it.
    """
    signal = _account_signal(candidate)
    if not signal:
        return None
    row = conn.execute(
        """INSERT INTO account_balances(
               workspace_id,account_id,account_name,bank_name,institution_code,
               institution_country,account_type,account_last4,currency,current_balance,
               source,include_in_net_worth,is_active,ownership_status,detected_at,last_seen_at,signals_count
           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,0,'finva_email_discovery',FALSE,TRUE,
                    'pending',NOW(),NOW(),1)
           ON CONFLICT(workspace_id,account_id,institution_code,account_last4,currency)
               WHERE account_id IS NOT NULL AND account_last4 IS NOT NULL AND account_last4<>''
           DO UPDATE SET
               last_seen_at=NOW(),signals_count=account_balances.signals_count+1,
               account_name=CASE WHEN account_balances.source='finva_email_discovery'
                                 THEN EXCLUDED.account_name ELSE account_balances.account_name END,
               updated_at=NOW()
           RETURNING id""",
        (
            workspace_id, account_id, signal["account_name"],
            signal["institution_name"], signal["institution_code"],
            signal["institution_country"], signal["account_type"],
            signal["account_last4"], signal["currency"],
        ),
    ).fetchone()
    financial_account_id = int(row["id"])
    conn.execute(
        """UPDATE finva_email_candidates SET financial_account_id=%s,updated_at=NOW()
           WHERE id=%s AND account_id=%s AND workspace_id=%s""",
        (financial_account_id, candidate_id, account_id, workspace_id),
    )
    return financial_account_id


def list_financial_identity() -> dict[str, Any]:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,account_name,bank_name,institution_code,institution_country,
                      account_type,account_last4,currency,ownership_status,
                      ownership_confirmed_at,detected_at,last_seen_at,signals_count,source
               FROM account_balances
               WHERE account_id=%s AND workspace_id=%s AND is_active=TRUE
               ORDER BY CASE ownership_status WHEN 'pending' THEN 0 WHEN 'own' THEN 1 ELSE 2 END,
                        bank_name,account_name,id""",
            (account_id, workspace_id),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {
        "status": "ok",
        "items": items,
        "summary": {
            "total": len(items),
            "pending": sum(item["ownership_status"] == "pending" for item in items),
            "owned": sum(item["ownership_status"] == "own" for item in items),
            "not_mine": sum(item["ownership_status"] == "not_mine" for item in items),
        },
    }


def confirm_financial_account(account_balance_id: int, ownership_status: str, display_name: str | None = None) -> dict[str, Any]:
    if ownership_status not in {"own", "not_mine"}:
        raise HTTPException(status_code=422, detail="La propiedad debe confirmarse como propia o ajena.")
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    name = (display_name or "").strip()
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE account_balances
               SET ownership_status=%s,ownership_confirmed_at=NOW(),
                   account_name=CASE WHEN %s<>'' THEN %s ELSE account_name END,
                   include_in_net_worth=CASE WHEN %s='not_mine' THEN FALSE ELSE include_in_net_worth END,
                   updated_at=NOW()
               WHERE id=%s AND account_id=%s AND workspace_id=%s AND is_active=TRUE
               RETURNING id,account_name,bank_name,institution_code,institution_country,
                         account_type,account_last4,currency,ownership_status,
                         ownership_confirmed_at,detected_at,last_seen_at,signals_count,source""",
            (ownership_status, name, name[:120], ownership_status, account_balance_id, account_id, workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cuenta financiera no encontrada.")
        if ownership_status == "not_mine":
            conn.execute(
                """UPDATE finva_email_candidates SET financial_account_id=NULL,updated_at=NOW()
                   WHERE financial_account_id=%s AND account_id=%s AND workspace_id=%s""",
                (account_balance_id, account_id, workspace_id),
            )
        from backend.user_product.candidate_resolution import reevaluate_workspace_candidates
        reevaluate_workspace_candidates(conn, account_id=account_id, workspace_id=workspace_id)
        conn.commit()
    return {"status": "ok", "item": dict(row)}
