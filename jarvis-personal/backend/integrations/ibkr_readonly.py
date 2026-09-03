from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.core.database import get_connection, serialize_row, serialize_rows


router = APIRouter(prefix="/integrations/ibkr", tags=["IBKR read-only"])


class IbkrPosition(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    sec_type: str = "STK"
    currency: str = "USD"
    exchange: str | None = None
    position: float = 0
    average_cost: float = 0
    market_price: float = 0
    market_value: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0


class IbkrSnapshot(BaseModel):
    captured_at: datetime
    account_id: str = Field(min_length=2, max_length=40)
    account_mode: Literal["paper", "live"] = "paper"
    base_currency: str = "USD"
    net_liquidation: float = 0
    cash: float = 0
    buying_power: float = 0
    gross_position_value: float = 0
    accrued_cash: float = 0
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    dividends: float = 0
    commissions: float = 0
    positions: list[IbkrPosition] = Field(default_factory=list, max_length=500)
    exchange_rate_crc: float | None = Field(default=None, gt=0)


def ensure_ibkr_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exchange_rates (
            id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1,
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            rate_date DATE NOT NULL, currency TEXT NOT NULL,
            exchange_rate NUMERIC(14,6) NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, rate_date, currency)
        )
        """
    )
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS snapshot_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS cash NUMERIC(18,4) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS buying_power NUMERIC(18,4) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS gross_position_value NUMERIC(18,4) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS accrued_cash NUMERIC(18,4) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS account_id_masked TEXT")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS account_mode TEXT NOT NULL DEFAULT 'manual'")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS snapshot_key TEXT")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS included_in_net_worth BOOLEAN NOT NULL DEFAULT TRUE")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS exchange_rate_crc NUMERIC(14,6)")
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS market_value_crc NUMERIC(18,2)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_ibkr_snapshot_key ON investment_portfolio_snapshots(workspace_id, snapshot_key) WHERE snapshot_key IS NOT NULL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS investment_position_snapshots (
            id BIGSERIAL PRIMARY KEY,
            workspace_id UUID NOT NULL,
            portfolio_snapshot_id BIGINT NOT NULL REFERENCES investment_portfolio_snapshots(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            sec_type TEXT NOT NULL,
            currency TEXT NOT NULL,
            exchange TEXT,
            position NUMERIC(24,8) NOT NULL DEFAULT 0,
            average_cost NUMERIC(18,6) NOT NULL DEFAULT 0,
            market_price NUMERIC(18,6) NOT NULL DEFAULT 0,
            market_value NUMERIC(18,4) NOT NULL DEFAULT 0,
            unrealized_pnl NUMERIC(18,4) NOT NULL DEFAULT 0,
            realized_pnl NUMERIC(18,4) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ibkr_positions_snapshot ON investment_position_snapshots(portfolio_snapshot_id)")


def _owner_identity(conn) -> tuple[int, str]:
    owner_email = (
        os.getenv("OWNER_EMAIL", "").strip()
        or next((value.strip() for value in os.getenv("OWNER_EMAILS", "").split(",") if value.strip()), "")
    ).lower()
    if not owner_email:
        raise RuntimeError("OWNER_EMAIL no está configurado.")
    row = conn.execute(
        """
        SELECT u.id AS user_id, w.id AS workspace_id
        FROM users u
        JOIN accounts a ON a.legacy_allowed_user_id = u.id
        JOIN workspaces w ON w.owner_account_id = a.id AND w.workspace_type = 'personal'
        WHERE LOWER(u.email) = %s
        ORDER BY w.created_at, w.id
        LIMIT 1
        """,
        (owner_email,),
    ).fetchone()
    if not row:
        raise RuntimeError("No encontré el workspace personal del owner.")
    return int(row["user_id"]), str(row["workspace_id"])


def _masked_account(account_id: str) -> str:
    clean = account_id.strip()
    return f"***{clean[-4:]}" if len(clean) > 4 else "***"


@router.post("/snapshot")
def receive_ibkr_snapshot(
    payload: IbkrSnapshot,
    x_jarvis_ibkr_secret: str | None = Header(default=None),
):
    expected = os.getenv("IBKR_BRIDGE_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="IBKR_BRIDGE_SECRET no está configurado.")
    if not x_jarvis_ibkr_secret or not hmac.compare_digest(x_jarvis_ibkr_secret, expected):
        raise HTTPException(status_code=403, detail="Credencial del puente IBKR inválida.")

    captured_at = payload.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)
    snapshot_key = hashlib.sha256(
        f"{payload.account_id}|{captured_at.isoformat()}".encode("utf-8")
    ).hexdigest()

    with get_connection() as conn:
        ensure_ibkr_tables(conn)
        user_id, workspace_id = _owner_identity(conn)
        rate_row = conn.execute(
            """
            SELECT exchange_rate FROM exchange_rates
            WHERE workspace_id=%s AND currency='USD'
            ORDER BY rate_date DESC, id DESC LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        exchange_rate_crc = payload.exchange_rate_crc or float((rate_row or {}).get("exchange_rate") or os.getenv("USD_CRC_FALLBACK", "495"))
        market_value_crc = payload.net_liquidation * exchange_rate_crc
        row = conn.execute(
            """
            INSERT INTO investment_portfolio_snapshots (
                user_id, workspace_id, snapshot_date, snapshot_at, market_value,
                realized_pnl, unrealized_pnl, dividends, commissions, currency,
                source, cash, buying_power, gross_position_value, accrued_cash,
                account_id_masked, account_mode, snapshot_key, included_in_net_worth,
                exchange_rate_crc, market_value_crc
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                'ibkr_readonly',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (workspace_id, snapshot_key) WHERE snapshot_key IS NOT NULL
            DO UPDATE SET updated_at=NOW()
            RETURNING *
            """,
            (
                user_id, workspace_id, captured_at.date(), captured_at,
                payload.net_liquidation, payload.realized_pnl, payload.unrealized_pnl,
                payload.dividends, payload.commissions, payload.base_currency.upper(),
                payload.cash, payload.buying_power, payload.gross_position_value,
                payload.accrued_cash, _masked_account(payload.account_id),
                payload.account_mode, snapshot_key, payload.account_mode == "live",
                exchange_rate_crc, market_value_crc,
            ),
        ).fetchone()
        snapshot_id = int(row["id"])
        conn.execute("DELETE FROM investment_position_snapshots WHERE portfolio_snapshot_id=%s", (snapshot_id,))
        for position in payload.positions:
            conn.execute(
                """
                INSERT INTO investment_position_snapshots (
                    workspace_id, portfolio_snapshot_id, symbol, sec_type, currency,
                    exchange, position, average_cost, market_price, market_value,
                    unrealized_pnl, realized_pnl
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    workspace_id, snapshot_id, position.symbol.upper(), position.sec_type.upper(),
                    position.currency.upper(), position.exchange, position.position,
                    position.average_cost, position.market_price, position.market_value,
                    position.unrealized_pnl, position.realized_pnl,
                ),
            )
        conn.commit()

    return {
        "status": "OK",
        "snapshot_id": snapshot_id,
        "captured_at": captured_at.isoformat(),
        "positions": len(payload.positions),
        "account": _masked_account(payload.account_id),
        "account_mode": payload.account_mode,
        "read_only": True,
        "exchange_rate_crc": exchange_rate_crc,
    }


def latest_ibkr_snapshot(conn, workspace_id: str):
    ensure_ibkr_tables(conn)
    snapshot = conn.execute(
        """
        SELECT * FROM investment_portfolio_snapshots
        WHERE workspace_id=%s AND source='ibkr_readonly'
        ORDER BY snapshot_at DESC NULLS LAST, id DESC LIMIT 1
        """,
        (workspace_id,),
    ).fetchone()
    if not snapshot:
        return None, []
    positions = conn.execute(
        """
        SELECT symbol, sec_type, currency, exchange, position, average_cost,
               market_price, market_value, unrealized_pnl, realized_pnl
        FROM investment_position_snapshots
        WHERE portfolio_snapshot_id=%s
        ORDER BY market_value DESC, symbol
        """,
        (snapshot["id"],),
    ).fetchall()
    return serialize_row(snapshot), serialize_rows(positions)
