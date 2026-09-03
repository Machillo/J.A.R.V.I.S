from datetime import date, datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection, serialize_row, serialize_rows
from backend.integrations.ibkr_readonly import ensure_ibkr_tables, flex_is_configured, sync_flex_snapshot

router = APIRouter(prefix="/finance/investment-center", tags=["finance-investments"])


class CashflowRequest(BaseModel):
    flow_type: str
    amount: float = Field(gt=0)
    currency: str = "CRC"
    flow_date: Optional[date] = None
    source: str = "manual"
    description: Optional[str] = None


class SnapshotRequest(BaseModel):
    market_value: float = 0
    contributed_capital: float = 0
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    dividends: float = 0
    taxes: float = 0
    commissions: float = 0
    funding_fees: float = 0
    currency: str = "USD"
    snapshot_date: Optional[date] = None
    source: str = "manual"


def _summary(workspace_id: str):
    with get_connection() as conn:
        ensure_ibkr_tables(conn)
        snap = conn.execute(
            """
            SELECT * FROM investment_portfolio_snapshots
            WHERE workspace_id=%s
            ORDER BY snapshot_date DESC, id DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        positions = conn.execute(
            """
            SELECT symbol, sec_type, currency, exchange, position, average_cost,
                   market_price, market_value, unrealized_pnl, realized_pnl
            FROM investment_position_snapshots
            WHERE portfolio_snapshot_id=%s
            ORDER BY market_value DESC, symbol
            """,
            (snap["id"],),
        ).fetchall() if snap else []
        flows = conn.execute(
            """
            SELECT * FROM investment_cashflows
            WHERE workspace_id=%s
            ORDER BY flow_date DESC, id DESC
            LIMIT 100
            """,
            (workspace_id,),
        ).fetchall()
        reserve = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN flow_type='reserve' AND currency='CRC' THEN amount
                    WHEN flow_type='reserve_release' AND currency='CRC' THEN -amount
                    ELSE 0
                END
            ), 0) AS total
            FROM investment_cashflows
            WHERE workspace_id=%s
            """,
            (workspace_id,),
        ).fetchone()

    s = serialize_row(snap) or {}
    market = float(s.get("market_value") or 0)
    contributed = float(s.get("contributed_capital") or 0)
    realized = float(s.get("realized_pnl") or 0)
    unrealized = float(s.get("unrealized_pnl") or 0)
    dividends = float(s.get("dividends") or 0)
    taxes = float(s.get("taxes") or 0)
    commissions = float(s.get("commissions") or 0)
    funding = float(s.get("funding_fees") or 0)
    snapshot_at = s.get("snapshot_at") or s.get("created_at")
    age_seconds = None
    if snapshot_at:
        try:
            parsed_at = datetime.fromisoformat(str(snapshot_at).replace("Z", "+00:00"))
            age_seconds = max(0, int((datetime.now(timezone.utc) - parsed_at.astimezone(timezone.utc)).total_seconds()))
        except (TypeError, ValueError):
            pass
    is_ibkr = s.get("source") == "ibkr_readonly"
    sync_status = "manual_ready_for_ibkr"
    sync_method = s.get("sync_method") or "manual"
    if is_ibkr:
        fresh_seconds = 36 * 60 * 60 if sync_method == "flex" else 10 * 60
        sync_status = "current" if age_seconds is not None and age_seconds <= fresh_seconds else "stale"
    gross = realized + unrealized + dividends
    net = gross - taxes - commissions - funding
    return {
        "portfolio": s,
        "flows": serialize_rows(flows),
        "reserved_to_invest_crc": float((reserve or {}).get("total") or 0),
        "gross_pnl": round(gross, 2),
        "net_pnl": round(net, 2),
        "return_pct": round((net / contributed * 100), 2) if contributed else 0,
        "funding_model": {"wise_percent_estimate": 1.23, "wise_to_ibkr_fixed_usd": 1.13},
        "positions": serialize_rows(positions),
        "sync_status": sync_status,
        "snapshot_age_seconds": age_seconds,
        "read_only": is_ibkr,
        "sync_method": sync_method,
        "flex_configured": flex_is_configured(),
        "included_in_net_worth": bool(s.get("included_in_net_worth", True)),
    }


@router.get("")
def get_center():
    return _summary(get_current_workspace_id())


@router.post("/sync-ibkr")
def sync_ibkr():
    # The authentication middleware protects this route; Flex credentials never reach the browser.
    get_current_workspace_id()
    try:
        return sync_flex_snapshot()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/cashflows")
def add_cashflow(request: CashflowRequest):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO investment_cashflows(
                user_id, workspace_id, flow_date, flow_type, amount, currency, source, description
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                user_id,
                workspace_id,
                request.flow_date or date.today(),
                request.flow_type,
                request.amount,
                request.currency.upper(),
                request.source,
                request.description,
            ),
        ).fetchone()
        conn.commit()
    return serialize_row(row)


@router.post("/snapshots")
def add_snapshot(request: SnapshotRequest):
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO investment_portfolio_snapshots(
                user_id, workspace_id, snapshot_date, market_value, contributed_capital,
                realized_pnl, unrealized_pnl, dividends, taxes, commissions,
                funding_fees, currency, source
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                user_id,
                workspace_id,
                request.snapshot_date or date.today(),
                request.market_value,
                request.contributed_capital,
                request.realized_pnl,
                request.unrealized_pnl,
                request.dividends,
                request.taxes,
                request.commissions,
                request.funding_fees,
                request.currency.upper(),
                request.source,
            ),
        ).fetchone()
        conn.commit()
    return serialize_row(row)
