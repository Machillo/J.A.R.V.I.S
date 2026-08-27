from datetime import date
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter

from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection, serialize_row, serialize_rows

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


def _summary(user_id: int):
    with get_connection() as conn:
        snap = conn.execute("""
            SELECT * FROM investment_portfolio_snapshots
            WHERE user_id=%s ORDER BY snapshot_date DESC, id DESC LIMIT 1
        """, (user_id,)).fetchone()
        flows = conn.execute("""
            SELECT * FROM investment_cashflows
            WHERE user_id=%s ORDER BY flow_date DESC, id DESC LIMIT 100
        """, (user_id,)).fetchall()
        reserve = conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN flow_type='reserve' AND currency='CRC' THEN amount
                 WHEN flow_type='reserve_release' AND currency='CRC' THEN -amount ELSE 0 END),0) total
            FROM investment_cashflows WHERE user_id=%s
        """, (user_id,)).fetchone()
    s = serialize_row(snap) or {}
    market = float(s.get("market_value") or 0)
    contributed = float(s.get("contributed_capital") or 0)
    realized = float(s.get("realized_pnl") or 0)
    unrealized = float(s.get("unrealized_pnl") or 0)
    dividends = float(s.get("dividends") or 0)
    taxes = float(s.get("taxes") or 0)
    commissions = float(s.get("commissions") or 0)
    funding = float(s.get("funding_fees") or 0)
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
        "sync_status": "manual_ready_for_ibkr",
    }

@router.get("")
def get_center():
    return _summary(get_current_user_id())

@router.post("/cashflows")
def add_cashflow(request: CashflowRequest):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute("""
            INSERT INTO investment_cashflows(user_id,flow_date,flow_type,amount,currency,source,description)
            VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """, (user_id, request.flow_date or date.today(), request.flow_type, request.amount,
              request.currency.upper(), request.source, request.description)).fetchone()
        conn.commit()
    return serialize_row(row)

@router.post("/snapshots")
def add_snapshot(request: SnapshotRequest):
    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute("""
            INSERT INTO investment_portfolio_snapshots(
              user_id,snapshot_date,market_value,contributed_capital,realized_pnl,unrealized_pnl,
              dividends,taxes,commissions,funding_fees,currency,source)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """, (user_id, request.snapshot_date or date.today(), request.market_value,
              request.contributed_capital, request.realized_pnl, request.unrealized_pnl,
              request.dividends, request.taxes, request.commissions, request.funding_fees,
              request.currency.upper(), request.source)).fetchone()
        conn.commit()
    return serialize_row(row)
