"""JARVIS IBKR bridge: account reads only; contains no order operations."""
from __future__ import annotations

import argparse
import os
import threading
import time
from datetime import datetime, timezone

import requests
from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class ReadOnlyAccount(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.downloaded = threading.Event()
        self.accounts: list[str] = []
        self.values: dict[str, float] = {}
        self.currency = "USD"
        self.positions: list[dict] = []

    def nextValidId(self, orderId):  # noqa: N802 - IBKR callback name
        self.ready.set()

    def managedAccounts(self, accountsList):  # noqa: N802
        self.accounts = [value.strip() for value in accountsList.split(",") if value.strip()]

    def updateAccountValue(self, key, value, currency, accountName):  # noqa: N802
        if currency and currency != "BASE":
            self.currency = currency
        try:
            self.values[key] = float(value)
        except (TypeError, ValueError):
            pass

    def updatePortfolio(self, contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName):  # noqa: N802,E501
        self.positions.append({
            "symbol": contract.symbol,
            "sec_type": contract.secType,
            "currency": contract.currency,
            "exchange": contract.primaryExchange or contract.exchange or None,
            "position": position,
            "average_cost": averageCost,
            "market_price": marketPrice,
            "market_value": marketValue,
            "unrealized_pnl": unrealizedPNL,
            "realized_pnl": realizedPNL,
        })

    def accountDownloadEnd(self, accountName):  # noqa: N802
        self.downloaded.set()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):  # noqa: N802
        if errorCode not in {2104, 2106, 2158}:
            print(f"IBKR {errorCode}: {errorString}")


def collect_snapshot(host: str, port: int, client_id: int, mode: str) -> dict:
    app = ReadOnlyAccount()
    app.connect(host, port, clientId=client_id)
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    if not app.ready.wait(15):
        app.disconnect()
        raise RuntimeError("IBKR no respondió. Verifica TWS/Gateway y el puerto API.")
    deadline = time.time() + 10
    while not app.accounts and time.time() < deadline:
        time.sleep(0.1)
    if not app.accounts:
        app.disconnect()
        raise RuntimeError("IBKR no devolvió una cuenta administrada.")
    account = app.accounts[0]
    app.reqAccountUpdates(True, account)
    if not app.downloaded.wait(20):
        app.disconnect()
        raise RuntimeError("IBKR no terminó de descargar el resumen de cuenta.")
    app.reqAccountUpdates(False, account)
    app.disconnect()
    value = lambda *keys: next((app.values[key] for key in keys if key in app.values), 0.0)
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account,
        "account_mode": mode,
        "base_currency": app.currency,
        "net_liquidation": value("NetLiquidation"),
        "cash": value("TotalCashValue", "CashBalance"),
        "buying_power": value("BuyingPower"),
        "gross_position_value": value("GrossPositionValue"),
        "accrued_cash": value("AccruedCash"),
        "realized_pnl": value("RealizedPnL"),
        "unrealized_pnl": value("UnrealizedPnL"),
        "dividends": value("NetDividend"),
        "commissions": 0,
        "positions": app.positions,
    }
    configured_rate = os.getenv("IBKR_USD_CRC_RATE")
    if configured_rate:
        snapshot["exchange_rate_crc"] = float(configured_rate)
    return snapshot


def publish(snapshot: dict, api_url: str, secret: str) -> None:
    response = requests.post(
        f"{api_url.rstrip('/')}/integrations/ibkr/snapshot",
        json=snapshot,
        headers={"X-Jarvis-IBKR-Secret": secret},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    print(f"JARVIS OK: {result['account']} · {result['positions']} posiciones · {result['captured_at']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Puente read-only IBKR → JARVIS")
    parser.add_argument("--interval", type=int, default=0, help="Segundos entre snapshots; 0 ejecuta una vez")
    args = parser.parse_args()
    api_url = os.environ["JARVIS_API_URL"]
    secret = os.environ["JARVIS_IBKR_BRIDGE_SECRET"]
    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "7497"))
    client_id = int(os.getenv("IB_CLIENT_ID", "902"))
    mode = os.getenv("IBKR_ACCOUNT_MODE", "paper").lower()
    if mode not in {"paper", "live"}:
        raise ValueError("IBKR_ACCOUNT_MODE debe ser paper o live.")
    while True:
        publish(collect_snapshot(host, port, client_id, mode), api_url, secret)
        if args.interval <= 0:
            break
        time.sleep(max(args.interval, 60))


if __name__ == "__main__":
    main()
