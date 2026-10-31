"""Patrimonio (VIP and the Owner): what you have and what you owe, from what is recorded.

- accounts: the active accounts marked to count in net worth (``account_balances``,
  ``include_in_net_worth``), at their declared balance plus the movements recorded after it
  (``balance_movements``, the rule every balance uses), in colones at the latest recorded rate;
  another currency without a rate stays unknown, never 1:1. A negative balance is owed.
- Salvavidas: the emergency fund as its screen counts it (``get_salvavidas_state``: declared plus
  automatic contributions). Its linked account (``account_type='emergency_fund'``) is not counted
  again as an account. An unknown Salvavidas stays unknown, not ₡0.
- investments: the latest live IBKR snapshot marked for net worth, else the recorded investments.
- debts: what is left of every active debt.

Net worth is assets minus debts, and only when every part is known (``complete``); otherwise the
known parts are listed and the unknown ones named. Read-only: every statement only reads, scoped
by the workspace.
"""
from __future__ import annotations

from typing import Any

from backend.auth.current_user import get_current_workspace_id
from backend.core.database import get_connection
from backend.finance import balance_movements
from backend.finance.emergency_fund import get_salvavidas_state


def _money(value: Any) -> float | None:
    return None if value is None else round(float(value), 2)


def _exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (f"public.{table}",)).fetchone()["name"])


def get_wealth() -> dict[str, Any]:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        accounts = _accounts(conn, workspace_id) if _exists(conn, "account_balances") else []
        investments = _investments(conn, workspace_id)
        debts = [dict(row) for row in conn.execute(
            """SELECT id, name, remaining_amount FROM debts
               WHERE workspace_id=%s AND (remaining_amount IS NULL OR remaining_amount > 0.01)
               ORDER BY remaining_amount DESC NULLS LAST, id""",
            (workspace_id,),
        ).fetchall()]
    try:
        salvavidas_state = get_salvavidas_state() or {}
    except Exception:
        salvavidas_state = {}
    salvavidas_amount = salvavidas_state.get("current_amount") if salvavidas_state else None
    salvavidas = {"name": "Salvavidas", "amount": _money(salvavidas_amount)}

    owned = [row for row in accounts if row["amount"] is None or row["amount"] >= 0]
    overdrawn = [{**row, "amount": round(-row["amount"], 2)} for row in accounts if row["amount"] is not None and row["amount"] < 0]
    debt_rows = [{"id": row["id"], "name": row["name"], "amount": _money(row["remaining_amount"])} for row in debts]
    asset_parts = [row["amount"] for row in owned] + [salvavidas["amount"]] + [row["amount"] for row in investments]
    liability_parts = [row["amount"] for row in debt_rows] + [row["amount"] for row in overdrawn]
    unknown = ([row["name"] for row in owned if row["amount"] is None] + ([] if salvavidas["amount"] is not None else ["Salvavidas"])
               + [row["name"] for row in investments if row["amount"] is None] + [row["name"] for row in debt_rows if row["amount"] is None])
    assets_total = round(sum(part for part in asset_parts if part is not None), 2)
    liabilities_total = round(sum(part for part in liability_parts if part is not None), 2)
    complete = not unknown
    return {
        "assets": {"accounts": owned, "salvavidas": salvavidas, "investments": investments, "total": assets_total},
        "liabilities": {"debts": debt_rows, "accounts": overdrawn, "total": liabilities_total},
        "net_worth": round(assets_total - liabilities_total, 2) if complete else None,
        "complete": complete,
        "unknown": unknown,
    }


def _accounts(conn, workspace_id: str) -> list[dict[str, Any]]:
    rate = ("""(SELECT exchange_rate FROM exchange_rates r WHERE r.workspace_id=a.workspace_id AND r.currency=a.currency
               ORDER BY rate_date DESC, id DESC LIMIT 1)""" if _exists(conn, "exchange_rates") else "NULL::numeric")
    rows = conn.execute(
        f"""SELECT a.id, a.account_name AS name, a.account_type, a.currency,
                   a.current_balance + COALESCE(m.movement_delta, 0) AS balance,
                   CASE WHEN a.currency='CRC' THEN 1 ELSE {rate} END AS rate
            FROM account_balances a
            LEFT JOIN LATERAL ({balance_movements.movements_since_declaration_sql("a")}) m ON TRUE
            WHERE a.workspace_id=%s AND a.is_active=TRUE AND a.include_in_net_worth=TRUE
              AND COALESCE(a.account_type,'') <> 'emergency_fund'
            ORDER BY a.id""",
        (workspace_id,),
    ).fetchall()
    result = []
    for row in rows:
        known = row["balance"] is not None and row["rate"] is not None
        result.append({
            "id": row["id"], "name": row["name"], "account_type": row["account_type"], "currency": row["currency"],
            "original_amount": _money(row["balance"]),
            "amount": round(float(row["balance"]) * float(row["rate"]), 2) if known else None,
        })
    return result


def _investments(conn, workspace_id: str) -> list[dict[str, Any]]:
    if _exists(conn, "investment_portfolio_snapshots"):
        live = conn.execute(
            """SELECT COALESCE(market_value_crc, market_value) AS amount, account_id_masked
               FROM investment_portfolio_snapshots
               WHERE workspace_id=%s AND source='ibkr_readonly' AND account_mode='live' AND included_in_net_worth=TRUE
               ORDER BY snapshot_at DESC NULLS LAST, snapshot_date DESC, id DESC LIMIT 1""",
            (workspace_id,),
        ).fetchone()
        if live:
            return [{"name": f"IBKR {live.get('account_id_masked') or ''}".strip(), "amount": _money(live["amount"])}]
    if not _exists(conn, "investments"):
        return []
    return [{"name": row["name"], "amount": _money(row["amount"])} for row in conn.execute(
        "SELECT name, amount FROM investments WHERE workspace_id=%s AND amount IS NOT NULL ORDER BY id DESC", (workspace_id,),
    ).fetchall()]
