"""Plan de dividendos (Owner; JARVIS → Patrimonio): how much capital a monthly dividend goal needs.

The Owner picks one or two stocks, the share of each, the yearly dividend yield of each (the app has
no market data and never picks a stock) and a monthly goal. Stored as the workspace's
`dividend_plan` preference. The calculation is deterministic and reads only: it assumes prices and
dividends stay as they are and that net dividends are reinvested, and it says so on screen.

Unknown is never 0: without a snapshot the value held is unknown, and without a yield there is no
capital figure. Stocks are bought only when the gate agreed with the Owner is open (no debt at 10%
a year or more, and a Salvavidas of 3 months or more); the calculation itself stays available.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

import requests
from fastapi import HTTPException

PREFERENCE_KEY = "dividend_plan"
DEFAULT_GOAL_MONTHLY_USD = 1000.0
# Costa Rica has no tax treaty with the US: the general withholding, editable until the broker confirms it.
DEFAULT_WITHHOLDING_PCT = 30.0
MAX_STOCK_DEBT_APR = 10.0
STOCK_SALVAVIDAS_MONTHS = 3
HORIZON_YEARS = (10, 15, 20)
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
HOLDING_TYPES = {"STK", "ETF"}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _in_range(value: Any, low: float, high: float) -> float | None:
    number = _number(value)
    return number if number is not None and low <= number <= high else None


def normalize(raw: Any) -> dict[str, Any]:
    """The stored values that can be used; anything invalid is unknown."""
    raw = raw if isinstance(raw, dict) else {}
    stocks = []
    for row in raw.get("stocks") if isinstance(raw.get("stocks"), list) else []:
        symbol = str(row.get("symbol") or "").strip().upper() if isinstance(row, dict) else ""
        share = _in_range(row.get("share_pct"), 0.01, 100) if isinstance(row, dict) else None
        if _SYMBOL.match(symbol) and share is not None:
            stocks.append({"symbol": symbol, "share_pct": share, "yield_pct": _in_range(row.get("yield_pct"), 0.01, 25)})
    return {
        "stocks": stocks[:2],
        "goal_monthly_usd": _in_range(raw.get("goal_monthly_usd"), 1, 1_000_000) or DEFAULT_GOAL_MONTHLY_USD,
        "monthly_amount_usd": _in_range(raw.get("monthly_amount_usd"), 0, 1_000_000),
        "withholding_pct": w if (w := _in_range(raw.get("withholding_pct"), 0, 60)) is not None else DEFAULT_WITHHOLDING_PCT,
    }


def validated(payload: dict[str, Any]) -> dict[str, Any]:
    """The configuration to store, or 422: nothing invalid is silently dropped from a save."""
    stocks = payload.get("stocks")
    if not isinstance(stocks, list) or not 1 <= len(stocks) <= 2:
        raise HTTPException(status_code=422, detail="Elegí una o dos acciones.")
    config = normalize(payload)
    if len(config["stocks"]) != len(stocks):
        raise HTTPException(status_code=422, detail="Revisá el símbolo y el porcentaje de cada acción.")
    if len({stock["symbol"] for stock in config["stocks"]}) != len(stocks):
        raise HTTPException(status_code=422, detail="Las dos acciones tienen que ser distintas.")
    if abs(sum(stock["share_pct"] for stock in config["stocks"]) - 100) > 0.001:
        raise HTTPException(status_code=422, detail="Los porcentajes tienen que sumar 100.")
    for original, stock in zip(stocks, config["stocks"]):
        if original.get("yield_pct") is not None and stock["yield_pct"] is None:
            raise HTTPException(status_code=422, detail="El dividendo anual va de 0,01% a 25%.")
    for key, label in (("goal_monthly_usd", "La meta"), ("monthly_amount_usd", "El monto mensual"), ("withholding_pct", "La retención")):
        if payload.get(key) is not None and _number(payload.get(key)) != config[key]:
            raise HTTPException(status_code=422, detail=f"{label} no es válida.")
    return config


def stock_gate(debts: list[dict[str, Any]], salvavidas: dict[str, Any]) -> dict[str, Any]:
    """Whether buying stocks is the plan's step now. What is unknown keeps it closed and is named."""
    blockers: list[dict[str, str]] = []
    active = [debt for debt in debts if (_number(debt.get("remaining_amount")) or 0) > 0.01]
    rates = [_number(debt.get("interest_rate")) for debt in active]
    if any(rate is None for rate in rates):
        blockers.append({"code": "debt_rate_unknown"})
    if any(rate is not None and rate >= MAX_STOCK_DEBT_APR for rate in rates):
        blockers.append({"code": "expensive_debt"})
    saved = _number(salvavidas.get("current_amount"))
    monthly = _number(salvavidas.get("monthly_base"))
    if saved is None or monthly is None or monthly <= 0:
        blockers.append({"code": "salvavidas_unknown"})
    elif saved < monthly * STOCK_SALVAVIDAS_MONTHS:
        blockers.append({"code": "salvavidas_short"})
    return {"open": not blockers, "blockers": blockers}


def _months_to(target: float, value: float, rate: float, monthly: float) -> int | None:
    """Months until `value` reaches `target` adding `monthly` and reinvesting at the monthly `rate`."""
    if value >= target:
        return 0
    if value <= 0 and monthly <= 0:
        return None
    return math.ceil(math.log((target * rate + monthly) / (value * rate + monthly)) / math.log(1 + rate))


def _monthly_for(target: float, value: float, rate: float, years: int) -> float:
    growth = (1 + rate) ** (years * 12)
    return max((target - value * growth) * rate / (growth - 1), 0.0)


def calculate(config: dict[str, Any], positions: list[dict[str, Any]] | None, gate: dict[str, Any]) -> dict[str, Any]:
    """`positions` None: there is no snapshot, so what is held is unknown (not 0)."""
    stocks = config["stocks"]
    result: dict[str, Any] = {
        "ready": False, "blended_yield_pct": None, "net_yield_pct": None, "capital_needed_usd": None, "current_value_usd": None,
        "missing_usd": None, "net_monthly_dividend_now_usd": None, "months_to_goal": None, "monthly_needed": [], "buy_this_month": [],
    }
    if positions is not None:
        chosen = {stock["symbol"] for stock in stocks}
        result["current_value_usd"] = round(sum(
            _number(row.get("market_value")) or 0 for row in positions
            if str(row.get("symbol") or "").upper() in chosen and str(row.get("currency") or "").upper() == "USD"
        ), 2)
    if not stocks or any(stock["yield_pct"] is None for stock in stocks):
        return result
    blended = sum(stock["share_pct"] * stock["yield_pct"] for stock in stocks) / 100
    net = blended * (1 - config["withholding_pct"] / 100)
    if net <= 0:
        return result
    target = config["goal_monthly_usd"] * 12 / (net / 100)
    result.update(ready=True, blended_yield_pct=round(blended, 2), net_yield_pct=round(net, 2), capital_needed_usd=round(target, 2))
    amount = config["monthly_amount_usd"]
    if gate["open"] and amount:
        result["buy_this_month"] = [{"symbol": s["symbol"], "amount_usd": round(amount * s["share_pct"] / 100, 2)} for s in stocks]
    value = result["current_value_usd"]
    if value is None:
        return result
    rate = net / 100 / 12
    result["missing_usd"] = round(max(target - value, 0.0), 2)
    result["net_monthly_dividend_now_usd"] = round(value * rate, 2)
    result["monthly_needed"] = [{"years": years, "amount_usd": round(_monthly_for(target, value, rate, years), 2)} for years in HORIZON_YEARS]
    if amount is not None:
        result["months_to_goal"] = _months_to(target, value, rate, amount)
    return result


# The stock's yield, so the Owner doesn't have to look it up. Only the symbol goes out. An unofficial
# public service: when it fails or answers oddly the yield stays unknown and can be typed.
QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
MAX_PLAUSIBLE_YIELD_PCT = 25.0


def _yield_from_chart(symbol: str, payload: Any) -> dict[str, Any] | None:
    """The last 12 months of dividends over the price. No price or no dividends: unknown, never 0%."""
    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        dividends = (result.get("events") or {}).get("dividends") or {}
    except (KeyError, IndexError, TypeError):
        return None
    if str(meta.get("symbol") or "").upper() != symbol or str(meta.get("currency") or "").upper() != "USD":
        return None
    price = _number(meta.get("regularMarketPrice"))
    amounts = [_number(row.get("amount")) for row in dividends.values() if isinstance(row, dict)]
    if not price or price <= 0 or not amounts or any(amount is None or amount <= 0 for amount in amounts):
        return None
    annual = sum(amounts)
    pct = annual / price * 100
    if pct > MAX_PLAUSIBLE_YIELD_PCT:
        return None
    return {"symbol": symbol, "yield_pct": round(pct, 2), "annual_dividend_usd": round(annual, 4), "price_usd": round(price, 2),
            "payments": len(amounts), "as_of": date.today().isoformat(), "source": "yahoo_finance"}


def lookup_yield(raw_symbol: Any) -> dict[str, Any]:
    symbol = str(raw_symbol or "").strip().upper()
    if not _SYMBOL.match(symbol):
        raise HTTPException(status_code=422, detail="Revisá el símbolo de la acción.")
    try:
        response = requests.get(QUOTE_URL.format(symbol=symbol), params={"range": "1y", "interval": "1mo", "events": "div"},
                                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=15)
        found = _yield_from_chart(symbol, response.json()) if response.status_code == 200 else None
    except (requests.RequestException, ValueError):
        found = None
    if found is None:
        raise HTTPException(status_code=502, detail="No pudimos traer el dividendo de esa acción. Podés escribirlo vos.")
    return found


def goal_from_holdings(goal: Any, positions: list[dict[str, Any]] | None, previous: dict[str, Any]) -> dict[str, Any]:
    """The plan from one number, the monthly goal, and what he already holds: his largest two stocks in
    dollars, each with its share of what they are worth and the yield found. A yield not found stays
    unknown, and the answer then says so; it is never taken as 0."""
    wanted = _in_range(goal, 1, 1_000_000)
    if wanted is None:
        raise HTTPException(status_code=422, detail="Escribí cuánto querés ganar al mes.")
    held = [row for row in positions or [] if str(row.get("currency") or "").upper() == "USD"
            and str(row.get("sec_type") or "STK").upper() in HOLDING_TYPES and (_number(row.get("market_value")) or 0) > 0
            and _SYMBOL.match(str(row.get("symbol") or "").upper())]
    held = sorted(held, key=lambda row: -(_number(row.get("market_value")) or 0))[:2]
    if not held:
        raise HTTPException(status_code=422, detail="Todavía no tenés acciones en tu portafolio. Agregá una a mano en Cambiar acciones.")
    total = sum(_number(row.get("market_value")) or 0 for row in held)
    stocks = []
    for index, row in enumerate(held):
        symbol = str(row["symbol"]).upper()
        share = round((_number(row.get("market_value")) or 0) / total * 100, 2) if index < len(held) - 1 else round(100 - sum(s["share_pct"] for s in stocks), 2)
        try:
            found = lookup_yield(symbol)["yield_pct"]
        except HTTPException:
            found = None
        stocks.append({"symbol": symbol, "share_pct": share, "yield_pct": found})
    return {**previous, "stocks": stocks, "goal_monthly_usd": wanted}
