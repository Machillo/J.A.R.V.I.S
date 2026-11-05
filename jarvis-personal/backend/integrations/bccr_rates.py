"""The dollar's daily selling rate (the Banco Central's published figure), with no account or token.

Two public services, and only a date range goes out: nothing about any user.
- Ministerio de Hacienda (`/indicadores/tc/dolar`): today's official rate. It wins on any day it covers.
- Frankfurter (its BCCR provider): the recent days, so a failed run or a close that ended days ago
  still finds its rate. It is a third party that republishes the same figure.

The rates are public and shared, so `market_exchange_rates` has no account or workspace.
`POST /integrations/exchange-rates/cron` is the scheduled command (.github/workflows/exchange-rate-sync.yml):
it stores the recent rates, then converts the dollar expenses whose close has arrived
(`pending_conversion.close_due_periods`).

A day without a published rate stays unknown: nothing here invents or assumes one.
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import requests
from fastapi import APIRouter, Header, HTTPException

from backend.core import observability
from backend.core.database import get_connection
from backend.core.time import costa_rica_today

router = APIRouter(prefix="/integrations/exchange-rates", tags=["integrations"])
logger = logging.getLogger(__name__)

HACIENDA_URL = "https://api.hacienda.go.cr/indicadores/tc/dolar"
HISTORY_URL = "https://api.frankfurter.dev/v2/rates"
CURRENCY, RATE_TYPE = "USD", "sell"
SOURCE_TODAY, SOURCE_HISTORY = "hacienda", "frankfurter_bccr"
# Long enough to cover a whole card cycle and to recover from failed runs.
FETCH_DAYS = 45
# A day without a published rate (a holiday, a late publication) may use the previous one, this far back.
MAX_RATE_AGE_DAYS = 7
# Colones per dollar: anything else is not this series, and is never stored.
MIN_RATE, MAX_RATE = Decimal("100"), Decimal("5000")


class RateFeedError(RuntimeError):
    """A service did not give usable rates."""


def _usable(day: Any, value: Any) -> tuple[date, Decimal] | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        parsed, rate = date.fromisoformat(str(day)[:10]), Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None
    return (parsed, rate) if rate.is_finite() and MIN_RATE <= rate <= MAX_RATE else None


def parse_today(payload: Any) -> list[tuple[date, Decimal]]:
    """Hacienda's `{"venta": {"fecha", "valor"}, "compra": ...}`: only the selling rate."""
    sell = payload.get("venta") if isinstance(payload, dict) else None
    if not isinstance(sell, dict):
        raise RateFeedError("unexpected answer")
    row = _usable(sell.get("fecha"), sell.get("valor"))
    return [row] if row else []


def parse_history(payload: Any) -> list[tuple[date, Decimal]]:
    """Frankfurter's `[{"date", "base", "quote", "rate"}]`: only dollars in colones."""
    if not isinstance(payload, list):
        raise RateFeedError("unexpected answer")
    rows = (_usable(row.get("date"), row.get("rate")) for row in payload
            if isinstance(row, dict) and row.get("base") == "USD" and row.get("quote") == "CRC")
    return [row for row in rows if row]


def _get_json(url: str, params: dict[str, str] | None = None) -> Any:
    response = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
    if response.status_code != 200:
        raise RateFeedError(f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise RateFeedError("not JSON") from exc


def fetch_today() -> list[tuple[date, Decimal]]:
    return parse_today(_get_json(HACIENDA_URL))


def fetch_history(start: date, end: date) -> list[tuple[date, Decimal]]:
    return parse_history(_get_json(HISTORY_URL, {"from": start.isoformat(), "to": end.isoformat(), "base": "USD", "quotes": "CRC", "providers": "BCCR"}))


def available(conn) -> bool:
    """False until the migration is applied: every reader then behaves as with no rates."""
    return bool(conn.execute("SELECT to_regclass('public.market_exchange_rates') AS present").fetchone()["present"])


def auto_close_active(conn) -> bool:
    """Whether the scheduled close is really running (a recent rate is stored), so the app only promises it then."""
    return latest_rate(conn) is not None


def store(conn, rows: list[tuple[date, Decimal]], source: str) -> None:
    for day, rate in rows:
        conn.execute(
            """INSERT INTO market_exchange_rates (rate_date, currency, rate_type, rate, source) VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (rate_date, currency, rate_type) DO UPDATE
               SET rate=EXCLUDED.rate, source=EXCLUDED.source, updated_at=NOW()
               RETURNING rate_date""",  # The connection adds `RETURNING id` otherwise, and this table has no id.
            (day, CURRENCY, RATE_TYPE, rate, source),
        )


def rates_between(conn, start: date, end: date) -> dict[date, Decimal]:
    """The stored selling rates from `MAX_RATE_AGE_DAYS` before `start` until `end`. Empty before the migration."""
    if not available(conn):
        return {}
    rows = conn.execute(
        "SELECT rate_date, rate FROM market_exchange_rates WHERE currency=%s AND rate_type=%s AND rate_date BETWEEN %s AND %s",
        (CURRENCY, RATE_TYPE, start - timedelta(days=MAX_RATE_AGE_DAYS), end),
    ).fetchall()
    return {date.fromisoformat(str(row["rate_date"])[:10]): Decimal(str(row["rate"])) for row in rows}


def rate_on_or_before(rates: dict[date, Decimal], day: date) -> Decimal | None:
    """The rate of `day`, or the closest earlier one not older than `MAX_RATE_AGE_DAYS`; else unknown."""
    for back in range(MAX_RATE_AGE_DAYS + 1):
        rate = rates.get(day - timedelta(days=back))
        if rate is not None:
            return rate
    return None


def closing_rate(rates: dict[date, Decimal], end: date, today: date) -> Decimal | None:
    """The rate a close converts with: the one of its last day. On that very day, if it is not
    published yet, the close waits for the next run instead of using yesterday's."""
    if end >= today:
        return rates.get(end)
    return rate_on_or_before(rates, end)


def latest_rate(conn) -> Decimal | None:
    """The newest stored rate, not older than `MAX_RATE_AGE_DAYS`."""
    today = costa_rica_today()
    rates = rates_between(conn, today, today)
    return rate_on_or_before(rates, today)


@router.post("/cron")
def sync_rates_cron(x_jarvis_cron_secret: str | None = Header(default=None)):
    # The same secret as the IBKR sync, so the scheduler needs no new setting.
    expected = os.getenv("IBKR_FLEX_CRON_SECRET", "").strip() or os.getenv("EMAIL_MONITOR_CRON_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="El cron no está configurado.")
    if not x_jarvis_cron_secret or not hmac.compare_digest(x_jarvis_cron_secret.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Credencial del cron inválida.")
    from backend.user_product.pending_conversion import close_due_periods

    today = costa_rica_today()
    fetched, failures = {}, []
    for source, fetch in ((SOURCE_HISTORY, lambda: fetch_history(today - timedelta(days=FETCH_DAYS), today)), (SOURCE_TODAY, fetch_today)):
        try:
            fetched[source] = fetch()
        except (RateFeedError, requests.RequestException) as exc:
            # Only the class. One service down does not stop the other.
            failures.append(source)
            logger.error("Exchange rate source failed source=%s type=%s", source, type(exc).__name__)
    if any(fetched.values()):
        with get_connection() as conn:
            for source, rows in fetched.items():  # today's official rate last: it wins on its day
                store(conn, rows, source)
            conn.commit()
    closed = close_due_periods(today)
    days = [day for rows in fetched.values() for day, _ in rows]
    observability.heartbeat("exchange_rates", ok=not failures and bool(days), error_class=",".join(failures) or None)
    if not days:
        raise HTTPException(status_code=502, detail="No se pudo leer el tipo de cambio.")
    return {"status": "OK", "latest_rate_date": max(days).isoformat(), "rates": len(set(days)), "failed_sources": len(failures), **closed}
