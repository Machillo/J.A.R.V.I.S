"""The dollar's daily selling rate, from the Banco Central de Costa Rica (SDDE API, indicator 318).

Only a date range goes out, with the server's token: nothing about any user. The rates are public
and shared, so `market_exchange_rates` has no account or workspace. `POST /integrations/exchange-rates/cron`
is the scheduled command (.github/workflows/exchange-rate-sync.yml): it stores the recent rates, then
converts the dollar expenses whose close has arrived (`pending_conversion.close_due_periods`).

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

SERIES_URL = "https://apim.bccr.fi.cr/SDDE/api/Bccr.GE.SDDE.Publico.Indicadores.API/indicadoresEconomicos/318/series"
TOKEN_ENV = "BCCR_API_TOKEN"
CURRENCY, RATE_TYPE, SOURCE = "USD", "sell", "bccr"
# Long enough to cover a whole card cycle and to recover from failed runs.
FETCH_DAYS = 45
# A day without a published rate (a holiday, a late publication) may use the previous one, this far back.
MAX_RATE_AGE_DAYS = 7
# Colones per dollar: anything else is not this series, and is never stored.
MIN_RATE, MAX_RATE = Decimal("100"), Decimal("5000")


class RateFeedError(RuntimeError):
    """The Banco Central did not give usable rates. Its message never holds the token."""


def parse_series(payload: Any) -> list[tuple[date, Decimal]]:
    """The usable (day, rate) rows of an answer. A refused or malformed answer raises; a day with no value is left out."""
    if not isinstance(payload, dict) or payload.get("estado") is not True or not isinstance(payload.get("datos"), list):
        raise RateFeedError("unexpected answer")
    item = next((row for row in payload["datos"] if isinstance(row, dict) and str(row.get("codigoIndicador")) == "318"), None)
    if item is None or not isinstance(item.get("series"), list):
        raise RateFeedError("no series")
    rows = []
    for serie in item["series"]:
        if not isinstance(serie, dict):
            continue
        value = serie.get("valorDatoPorPeriodo")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        try:
            day = date.fromisoformat(str(serie.get("fecha"))[:10])
            rate = Decimal(str(value))
        except (ValueError, ArithmeticError):
            continue
        if rate.is_finite() and MIN_RATE <= rate <= MAX_RATE:
            rows.append((day, rate))
    return rows


def fetch_series(start: date, end: date) -> list[tuple[date, Decimal]]:
    token = os.getenv(TOKEN_ENV, "").strip()
    if not token:
        raise RateFeedError("not configured")
    response = requests.get(
        SERIES_URL,
        params={"fechaInicio": start.strftime("%Y/%m/%d"), "fechaFin": end.strftime("%Y/%m/%d"), "idioma": "ES"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RateFeedError(f"HTTP {response.status_code}")
    try:
        return parse_series(response.json())
    except ValueError as exc:
        raise RateFeedError("not JSON") from exc


def available(conn) -> bool:
    """False until the migration is applied: every reader then behaves as with no rates."""
    return bool(conn.execute("SELECT to_regclass('public.market_exchange_rates') AS present").fetchone()["present"])


def auto_close_active(conn) -> bool:
    """Whether the scheduled close can run, so the app only promises it when it is true."""
    return available(conn) and bool(os.getenv(TOKEN_ENV, "").strip())


def store(conn, rows: list[tuple[date, Decimal]]) -> None:
    for day, rate in rows:
        conn.execute(
            """INSERT INTO market_exchange_rates (rate_date, currency, rate_type, rate, source) VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (rate_date, currency, rate_type) DO UPDATE
               SET rate=EXCLUDED.rate, source=EXCLUDED.source, updated_at=NOW()""",
            (day, CURRENCY, RATE_TYPE, rate, SOURCE),
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
    if not x_jarvis_cron_secret or not hmac.compare_digest(x_jarvis_cron_secret, expected):
        raise HTTPException(status_code=403, detail="Credencial del cron inválida.")
    from backend.user_product.pending_conversion import close_due_periods

    today = costa_rica_today()
    feed_error = None
    rows: list[tuple[date, Decimal]] = []
    try:
        rows = fetch_series(today - timedelta(days=FETCH_DAYS), today)
    except (RateFeedError, requests.RequestException) as exc:
        # Never the exception's text. The rates already stored can still close what is due.
        feed_error = type(exc).__name__
        logger.error("Exchange rate feed failed type=%s", feed_error)
    if rows:
        with get_connection() as conn:
            store(conn, rows)
            conn.commit()
    closed = close_due_periods(today)
    observability.heartbeat("exchange_rates", ok=feed_error is None, error_class=feed_error)
    if feed_error:
        raise HTTPException(status_code=502, detail="No se pudo leer el tipo de cambio del Banco Central.")
    if not rows:
        raise HTTPException(status_code=502, detail="El Banco Central no devolvió tipos de cambio.")
    return {"status": "OK", "latest_rate_date": max(day for day, _ in rows).isoformat(), "rates": len(rows), **closed}


