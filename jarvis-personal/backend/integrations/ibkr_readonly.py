from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
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


FLEX_SEND_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
FLEX_ALLOWED_HOSTS = {
    "ndcdyn.interactivebrokers.com",
    "gdcdyn.interactivebrokers.com",
    "www.interactivebrokers.com",
}
FLEX_PENDING_CODES = {"1018", "1019"}


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
    conn.execute("ALTER TABLE investment_portfolio_snapshots ADD COLUMN IF NOT EXISTS sync_method TEXT NOT NULL DEFAULT 'manual'")
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


def _number(value, default: float = 0) -> float:
    if value in (None, "", "--"):
        return default
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _attr(element: ET.Element | None, *names: str, default=None):
    if element is None:
        return default
    lowered = {key.lower(): value for key, value in element.attrib.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return default


def _elements(root: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == name]


def parse_flex_statement(xml_text: str, account_mode: Literal["paper", "live"] = "live") -> IbkrSnapshot:
    """Convert an IBKR Activity Flex Query XML response into JARVIS' read-only snapshot."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("IBKR devolvió un reporte Flex XML inválido.") from exc

    statements = _elements(root, "FlexStatement")
    statement = statements[-1] if statements else root
    account_id = str(_attr(statement, "accountId", "accountID", default="")).strip()
    if not account_id:
        account_info = next(iter(_elements(statement, "AccountInformation")), None)
        account_id = str(_attr(account_info, "accountId", "accountID", default="")).strip()
    if not account_id:
        raise ValueError("El Flex Query no incluye accountId.")

    generated = _attr(statement, "whenGenerated", "toDate")
    captured_at = datetime.now(timezone.utc)
    if generated:
        for fmt in ("%Y%m%d;%H%M%S", "%Y%m%d", "%Y-%m-%d;%H:%M:%S", "%Y-%m-%d"):
            try:
                captured_at = datetime.strptime(str(generated), fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue

    equity_rows = _elements(statement, "EquitySummaryByReportDateInBase")
    equity = equity_rows[-1] if equity_rows else None
    cash_rows = _elements(statement, "CashReportCurrency")
    base_cash = next(
        (row for row in reversed(cash_rows) if str(_attr(row, "currency", default="")).upper() in {"BASE_SUMMARY", "BASE"}),
        cash_rows[-1] if cash_rows else None,
    )
    account_info = next(iter(_elements(statement, "AccountInformation")), None)
    base_currency = str(
        _attr(statement, "currency", default=None)
        or _attr(account_info, "baseCurrency", "currency", default=None)
        or "USD"
    ).upper()

    cash = _number(_attr(equity, "cash", "totalCash"), _number(_attr(base_cash, "endingCash")))

    positions: list[IbkrPosition] = []
    for row in _elements(statement, "OpenPosition"):
        quantity = _number(_attr(row, "position", "quantity"))
        market_value = _number(_attr(row, "positionValue", "marketValue"))
        if not quantity and not market_value:
            continue
        symbol = str(_attr(row, "symbol", "description", default="POSICION")).strip()[:40]
        positions.append(IbkrPosition(
            symbol=symbol or "POSICION",
            sec_type=str(_attr(row, "assetCategory", "secType", default="STK")),
            currency=str(_attr(row, "currency", default=base_currency)),
            exchange=_attr(row, "listingExchange", "exchange"),
            position=quantity,
            average_cost=_number(_attr(row, "openPrice", "costBasisPrice")),
            market_price=_number(_attr(row, "markPrice", "marketPrice")),
            market_value=market_value,
            unrealized_pnl=_number(_attr(row, "fifoPnlUnrealized", "unrealizedPnl")),
            realized_pnl=_number(_attr(row, "fifoPnlRealized", "realizedPnl")),
        ))

    gross_position_value = sum(abs(position.market_value) for position in positions)
    net_liquidation = _number(_attr(equity, "netLiquidation", "total"))
    if not net_liquidation:
        net_liquidation = cash + sum(position.market_value for position in positions)
    unrealized_pnl = sum(position.unrealized_pnl for position in positions)
    realized_pnl = sum(_number(_attr(row, "fifoPnlRealized", "realizedPnl")) for row in _elements(statement, "Trade"))
    commissions = abs(sum(_number(_attr(row, "ibCommission", "commission")) for row in _elements(statement, "Trade")))
    dividends = sum(
        _number(_attr(row, "amount"))
        for row in _elements(statement, "CashTransaction")
        if "dividend" in str(_attr(row, "type", "description", default="")).lower()
    )

    return IbkrSnapshot(
        captured_at=captured_at,
        account_id=account_id,
        account_mode=account_mode,
        base_currency=base_currency,
        net_liquidation=net_liquidation,
        cash=cash,
        buying_power=_number(_attr(account_info, "buyingPower"), cash),
        gross_position_value=gross_position_value,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        dividends=dividends,
        commissions=commissions,
        positions=positions,
    )


def flex_is_configured() -> bool:
    return bool(os.getenv("IBKR_FLEX_TOKEN", "").strip() and os.getenv("IBKR_FLEX_QUERY_ID", "").strip())


def _flex_error(root: ET.Element) -> tuple[str, str]:
    code = next((element.text or "" for element in _elements(root, "ErrorCode")), "")
    message = next((element.text or "" for element in _elements(root, "ErrorMessage")), "")
    return code.strip(), message.strip()


def _flex_xml(response: requests.Response) -> ET.Element:
    response.raise_for_status()
    try:
        return ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise RuntimeError("IBKR devolvió una respuesta Flex inválida.") from exc


def _validate_flex_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host in FLEX_ALLOWED_HOSTS or host.endswith(".interactivebrokers.com")):
        raise RuntimeError("IBKR devolvió una URL Flex no permitida.")
    return value


def fetch_flex_statement() -> str:
    token = os.getenv("IBKR_FLEX_TOKEN", "").strip()
    query_id = os.getenv("IBKR_FLEX_QUERY_ID", "").strip()
    if not token or not query_id:
        raise RuntimeError("IBKR Flex todavía no está configurado en Render.")

    response = requests.get(FLEX_SEND_URL, params={"t": token, "q": query_id, "v": "3"}, timeout=30)
    root = _flex_xml(response)
    code, message = _flex_error(root)
    status = next((element.text or "" for element in _elements(root, "Status")), "")
    if status.strip().lower() != "success":
        raise RuntimeError(f"IBKR Flex rechazó la solicitud ({code or 'sin código'}): {message or 'sin detalle'}")
    reference = next((element.text or "" for element in _elements(root, "ReferenceCode")), "").strip()
    report_url = next((element.text or "" for element in _elements(root, "Url")), "").strip()
    if not reference or not report_url:
        raise RuntimeError("IBKR Flex no devolvió la referencia del reporte.")
    report_url = _validate_flex_url(report_url)

    for attempt in range(8):
        report_response = requests.get(report_url, params={"q": reference, "t": token, "v": "3"}, timeout=45)
        report_root = _flex_xml(report_response)
        report_code, report_message = _flex_error(report_root)
        if _elements(report_root, "FlexStatement"):
            return report_response.text
        if report_code in FLEX_PENDING_CODES and attempt < 7:
            time.sleep(2)
            continue
        raise RuntimeError(
            f"IBKR Flex no pudo generar el reporte ({report_code or 'sin código'}): "
            f"{report_message or 'sin detalle'}"
        )
    raise RuntimeError("IBKR Flex tardó demasiado en generar el reporte.")


def sync_flex_snapshot() -> dict:
    mode = os.getenv("IBKR_FLEX_ACCOUNT_MODE", "live").strip().lower()
    account_mode: Literal["paper", "live"] = "paper" if mode == "paper" else "live"
    payload = parse_flex_statement(fetch_flex_statement(), account_mode=account_mode)
    return _persist_snapshot(payload, sync_method="flex")


def _persist_snapshot(payload: IbkrSnapshot, sync_method: str = "bridge") -> dict:
    captured_at = payload.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)
    snapshot_key = hashlib.sha256(
        f"{sync_method}|{payload.account_id}|{captured_at.isoformat()}".encode("utf-8")
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
                exchange_rate_crc, market_value_crc, sync_method
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                'ibkr_readonly',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            ON CONFLICT (workspace_id, snapshot_key) WHERE snapshot_key IS NOT NULL
            DO UPDATE SET
                market_value=EXCLUDED.market_value,
                realized_pnl=EXCLUDED.realized_pnl,
                unrealized_pnl=EXCLUDED.unrealized_pnl,
                dividends=EXCLUDED.dividends,
                commissions=EXCLUDED.commissions,
                cash=EXCLUDED.cash,
                buying_power=EXCLUDED.buying_power,
                gross_position_value=EXCLUDED.gross_position_value,
                accrued_cash=EXCLUDED.accrued_cash,
                included_in_net_worth=EXCLUDED.included_in_net_worth,
                exchange_rate_crc=EXCLUDED.exchange_rate_crc,
                market_value_crc=EXCLUDED.market_value_crc,
                sync_method=EXCLUDED.sync_method,
                updated_at=NOW()
            RETURNING *
            """,
            (
                user_id, workspace_id, captured_at.date(), captured_at,
                payload.net_liquidation, payload.realized_pnl, payload.unrealized_pnl,
                payload.dividends, payload.commissions, payload.base_currency.upper(),
                payload.cash, payload.buying_power, payload.gross_position_value,
                payload.accrued_cash, _masked_account(payload.account_id),
                payload.account_mode, snapshot_key, payload.account_mode == "live",
                exchange_rate_crc, market_value_crc, sync_method,
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
        "status": "OK", "snapshot_id": snapshot_id,
        "captured_at": captured_at.isoformat(), "positions": len(payload.positions),
        "account": _masked_account(payload.account_id), "account_mode": payload.account_mode,
        "read_only": True, "exchange_rate_crc": exchange_rate_crc,
        "sync_method": sync_method,
    }


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

    return _persist_snapshot(payload, sync_method="bridge")


@router.post("/flex/cron")
def sync_flex_cron(x_jarvis_cron_secret: str | None = Header(default=None)):
    expected = os.getenv("IBKR_FLEX_CRON_SECRET", "").strip() or os.getenv("EMAIL_MONITOR_CRON_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="IBKR_FLEX_CRON_SECRET no está configurado.")
    if not x_jarvis_cron_secret or not hmac.compare_digest(x_jarvis_cron_secret, expected):
        raise HTTPException(status_code=403, detail="Credencial del cron IBKR inválida.")
    try:
        return sync_flex_snapshot()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
