"""Persistence and comparison for FINVA longitudinal financial state."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.financial_lifecycle.state import build_financial_state


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def capture_financial_snapshot() -> dict[str, Any]:
    state = build_financial_state()
    workspace_id = get_current_workspace_id()
    account_id = get_current_account_id()
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO financial_state_snapshots(
                   workspace_id,account_id,snapshot_date,period,schema_version,state
               ) VALUES(%s,%s,%s,%s,%s,%s::jsonb)
               ON CONFLICT(workspace_id,snapshot_date) DO UPDATE SET
                   account_id=EXCLUDED.account_id,
                   period=EXCLUDED.period,
                   schema_version=EXCLUDED.schema_version,
                   state=EXCLUDED.state,
                   captured_at=NOW()
               RETURNING id,snapshot_date,captured_at""",
            (workspace_id, account_id, date.today(), state["period"], state["schema_version"], payload),
        ).fetchone()
        conn.commit()
    return {"status": "OK", "snapshot": dict(row), "state": state}


def list_financial_snapshots(limit: int = 90) -> list[dict[str, Any]]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,snapshot_date,period,schema_version,state,captured_at
               FROM financial_state_snapshots
               WHERE workspace_id=%s
               ORDER BY snapshot_date DESC,id DESC LIMIT %s""",
            (workspace_id, max(1, min(int(limit or 90), 366))),
        ).fetchall()
    return [dict(row) for row in rows]


def get_financial_progress() -> dict[str, Any]:
    current = build_financial_state()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        previous = conn.execute(
            """SELECT snapshot_date,state
               FROM financial_state_snapshots
               WHERE workspace_id=%s AND snapshot_date < CURRENT_DATE
               ORDER BY snapshot_date DESC,id DESC LIMIT 1""",
            (workspace_id,),
        ).fetchone()

    if not previous:
        return {
            "status": "BASELINE",
            "current": current,
            "previous": None,
            "delta": None,
            "message": "FINVA necesita una observación anterior para medir progreso.",
        }

    prior = previous.get("state") or {}
    current_balance = current.get("balance_sheet") or {}
    prior_balance = prior.get("balance_sheet") or {}
    current_cash = current.get("cashflow") or {}
    prior_cash = prior.get("cashflow") or {}
    current_fund = current.get("emergency_fund") or {}
    prior_fund = prior.get("emergency_fund") or {}
    current_debt = current.get("debt") or {}
    prior_debt = prior.get("debt") or {}

    delta = {
        "net_worth": round(_n(current_balance.get("net_worth")) - _n(prior_balance.get("net_worth")), 2),
        "debt_total": round(_n(current_debt.get("total")) - _n(prior_debt.get("total")), 2),
        "liquid_assets": round(_n(current_balance.get("liquid_assets")) - _n(prior_balance.get("liquid_assets")), 2),
        "safe_available": round(_n(current_cash.get("safe_available")) - _n(prior_cash.get("safe_available")), 2),
        "emergency_coverage_months": round(_n(current_fund.get("coverage_months")) - _n(prior_fund.get("coverage_months")), 2),
        "health_score": round(_n((current.get("health") or {}).get("score")) - _n((prior.get("health") or {}).get("score")), 2),
    }
    strategy_changed = (current.get("strategy") or {}).get("next_action") != (prior.get("strategy") or {}).get("next_action")
    return {
        "status": "OK",
        "current": current,
        "previous": {"snapshot_date": previous.get("snapshot_date"), "state": prior},
        "delta": delta,
        "strategy_changed": strategy_changed,
    }
