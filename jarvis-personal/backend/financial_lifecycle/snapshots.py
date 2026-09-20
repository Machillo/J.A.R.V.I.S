"""Persistence and comparison for FINVA longitudinal financial state."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.financial_lifecycle.progress import build_longitudinal_progress, compare_states
from backend.financial_lifecycle.monthly_review import build_monthly_review
from backend.financial_lifecycle.state import build_financial_state

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
        history = conn.execute(
            """SELECT snapshot_date,state
               FROM financial_state_snapshots
               WHERE workspace_id=%s AND snapshot_date < CURRENT_DATE
                 AND snapshot_date >= CURRENT_DATE - INTERVAL '366 days'
               ORDER BY snapshot_date DESC,id DESC LIMIT 366""",
            (workspace_id,),
        ).fetchall()

    if not history:
        return {
            "status": "BASELINE",
            "current": current,
            "previous": None,
            "delta": None,
            "message": "FINVA necesita una observación anterior para medir progreso.",
            "longitudinal": build_longitudinal_progress(current, []),
        }

    previous = history[0]
    prior = previous.get("state") or {}
    comparison = compare_states(current, prior)
    delta = {name: item["delta"] for name, item in comparison["metrics"].items()}
    return {
        "status": "OK",
        "current": current,
        "previous": {"snapshot_date": previous.get("snapshot_date"), "state": prior},
        "delta": delta,
        "strategy_changed": comparison["strategy_transition"]["changed"],
        "comparison": comparison,
        "longitudinal": build_longitudinal_progress(current, history),
    }


def get_monthly_review(period: str | None = None) -> dict[str, Any]:
    today = date.today()
    selected = period or today.strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", selected):
        raise ValueError("El período debe usar el formato YYYY-MM.")
    year, month = (int(part) for part in selected.split("-"))
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT snapshot_date,state
               FROM financial_state_snapshots
               WHERE workspace_id=%s AND snapshot_date>=%s AND snapshot_date<%s
               ORDER BY snapshot_date ASC,id ASC""",
            (workspace_id, start, end),
        ).fetchall()
    observations = [dict(row) for row in rows]
    is_current = selected == today.strftime("%Y-%m")
    if is_current:
        closing_state = build_financial_state()
    elif observations:
        closing_state = observations[-1].get("state") or {}
    else:
        closing_state = {}
    return build_monthly_review(period=selected, closing_state=closing_state, observations=observations)
