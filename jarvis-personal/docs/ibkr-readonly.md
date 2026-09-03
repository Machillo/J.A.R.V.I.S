# JARVIS → IBKR read-only

La integración principal usa **IBKR Flex Web Service**: funciona desde Render sin una PC encendida, descarga un Activity Statement y guarda un snapshot diario. Flex es información de cierre/estado de cuenta; no debe mostrarse como cotización en vivo.

## Flex diario (recomendado)

1. En Client Portal de IBKR, crear un **Activity Flex Query** que incluya Account Information, Equity Summary, Cash Report, Open Positions, Trades y Cash Transactions.
2. Activar Flex Web Service y copiar el token y el Query ID.
3. Configurar en Render:

```text
IBKR_FLEX_TOKEN=<token-secreto>
IBKR_FLEX_QUERY_ID=<query-id>
IBKR_FLEX_ACCOUNT_MODE=live
IBKR_FLEX_CRON_SECRET=<secreto-largo>
USD_CRC_FALLBACK=495
```

El botón **Sincronizar IBKR** llama al backend autenticado. Para automatizarlo diariamente, un cron debe ejecutar:

```text
POST https://<render-service>.onrender.com/integrations/ibkr/flex/cron
X-Jarvis-Cron-Secret: <IBKR_FLEX_CRON_SECRET>
```

Una ejecución diaria después del cierre de mercado es suficiente. El token nunca se expone al frontend y el código no contiene operaciones para crear, modificar ni cancelar órdenes.

El puente local TWS/Gateway queda como alternativa opcional para snapshots intradía. Render no puede conectarse al TWS/Gateway de `127.0.0.1`.

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
