# JARVIS → IBKR read-only

JARVIS receives account snapshots from a local bridge because Render cannot connect to TWS/Gateway on `127.0.0.1`.

## Security boundary

- JARVIS uses client ID `902`; the KNT bot keeps client ID `901`.
- Enable **Read-Only API** in TWS/Gateway before running the bridge.
- The bridge contains no place, modify, cancel or global-cancel order calls.
- `paper` snapshots are visible in Investments but excluded from real net worth.
- Only `live` snapshots are included in net worth, converted with the latest saved USD→CRC rate.

## Render

Create a long random secret and add it as:

```text
IBKR_BRIDGE_SECRET=<random-secret>
USD_CRC_FALLBACK=495
```

## Windows bridge

From the repository root in PowerShell:

```powershell
py -m pip install -r jarvis-personal/scripts/requirements-ibkr-bridge.txt
$env:JARVIS_API_URL="https://<render-service>.onrender.com"
$env:JARVIS_IBKR_BRIDGE_SECRET="<same-random-secret>"
$env:IB_HOST="127.0.0.1"
$env:IB_PORT="7497"
$env:IB_CLIENT_ID="902"
$env:IBKR_ACCOUNT_MODE="paper"
py jarvis-personal/scripts/ibkr_readonly_bridge.py
```

For continuous updates every five minutes while TWS/Gateway is running:

```powershell
py jarvis-personal/scripts/ibkr_readonly_bridge.py --interval 300
```

For the real account, keep Read-Only API enabled, use its configured API port, and change only:

```powershell
$env:IBKR_ACCOUNT_MODE="live"
```

Optionally set `IBKR_USD_CRC_RATE`; otherwise JARVIS uses the newest USD rate already stored in Finance and finally `USD_CRC_FALLBACK`.
