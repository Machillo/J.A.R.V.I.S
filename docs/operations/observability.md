# Observabilidad y alertas de producción

Objetivo: enterarse de que algo falla en DINCR **antes** de que un usuario avise, con información accionable, **sin** filtrar secretos ni datos financieros y **sin** 200 mensajes iguales.

Código: `backend/core/observability.py` (núcleo), `backend/product_ops/observability_routes.py` (salud), `.github/workflows/uptime.yml` (sonda externa). Tests: `backend/tests/test_observability.py`.

---

## 1. Auditoría previa (qué había)

| | Pieza | Estado | Decisión |
|---|---|---|---|
| A/B | Incidentes reportados por la app (`POST /product-ops/incidents` → `feedback_reports`), dedupe por cuenta + huella en 5 min, presupuesto 5 alertas/cuenta/hora, Discord | Funciona y es seguro (validación de host del webhook, sin menciones, sin payloads) | **Se reutiliza tal cual.** Sigue siendo el canal de fallas que ve el usuario |
| A/B | Webhook Discord (`SUPPORT_DISCORD_WEBHOOK_URL`, `_discord_webhook_host`, rol solo en critical) | Bien diseñado | **Se reutiliza** la validación y el canal |
| A/B | Request ID (`X-Request-ID` validado `^[A-Za-z0-9_-]{8,80}$`, generado si falta, devuelto y expuesto por CORS) y `_safe_exception_summary` | Correcto | **Se reutiliza**; el resumen se movió a `core` para que otros módulos lo usen |
| A/B | PostHog backend (`server_error`, `mail_sync_*`) con lista blanca de propiedades | Correcto (analítica, no alertas) | Se mantiene |
| A/B | `GET /product-ops/health` (salud agregada de incidentes de clientes, caché 15 s) | Correcto, requiere sesión | Se mantiene |
| C | `/status`, `/auth/health`, `/` | Solo "el proceso responde", sin DB | Se agregan `/health/live` y `/health/ready` |
| C | Crons (notificaciones, tiendas, mantenimiento Gmail, IBKR) | Sin registro de última corrida; el mantenimiento Gmail **tragaba** fallas por conexión sin log | Heartbeat + reporte |
| C | `server_error` a PostHog | Solo desde los exception handlers de FastAPI: los 500 atrapados en `auth_middleware` (la mayoría) **no llegaban** | Corregido: todos los caminos reportan |
| D | — | No había sistemas duplicados de alertas | Se evitó crear uno: todo pasa por `report()` y el mismo Discord |
| F | Alertas del **servidor** (500, DB caída, proveedor caído, job fallando) | **No existían**: nada llegaba a Discord salvo que un cliente reportara | Nuevo: `report()` + `AlertGate` |
| F | Detectar que el backend está **totalmente caído** | Imposible desde adentro (los clientes reportan al mismo backend) | Nuevo: sonda externa (GitHub Actions) |
| F | Configuración de logging | **No existía** (`basicConfig`/`dictConfig` en ningún lado): los `logger.info` de la app probablemente no salen en Render | Loggers `dincr.ops` y `dincr.access` configurados; resto intacto |
| F | Privacidad del access log de uvicorn | Imprime la URL cruda: `?code=` de OAuth y `?token=` del push de Gmail | Filtro que quita la query string |
| F | Borrado de cuenta | `logger.exception` imprimía mensaje y traceback (pueden citar valores de filas) | Cambiado a resumen seguro |

Sin rate limiting en el backend (no hay 429 propios); fuera de alcance.

---

## 2. Arquitectura

```
                         ┌──────────── proceso backend (Render) ────────────┐
request ─► auth_middleware (request ID) ─► access_log_middleware ─► ruta     │
              │ 500 / auth sin veredicto            │ 1 línea JSON           │
              ▼                                     ▼  lento > 5 s          │
DB connect falla ─┐                         report(component, event, sev)    │
proveedor/job ────┼──────────────────────►   ├─ log JSON (dincr.ops)         │
cron heartbeat ───┘                          └─ AlertGate (huella, cooldown, │
                                                presupuesto, escalado,      │
/health/ready ─► sonda DB (conexión propia,     recuperación)               │
                 3 s, compartida 10 s)             │ pocas alertas           │
                 + jobs trabados (cada 10 min)     ▼                         │
                                              cola acotada (50) → hilo → Discord
                         └──────────────────────────────────────────────────┘
GitHub Actions (cada 10 min) ─► GET /health/ready ─► Discord solo en DOWN / RECOVERED
```

---

## 3. Severidades

Se amplía la escala existente (`info`, `warning`, `critical`) con `error` en medio. Los incidentes de clientes siguen igual.

| Severidad | Significado | Ejemplos |
|---|---|---|
| INFO | Evento normal relevante | usuario revocó el acceso a Gmail; request completo |
| WARNING | Degradación; todavía se opera | request lento; un buzón no sincronizó; 503 deliberado; notificaciones trabadas |
| ERROR | Funcionalidad importante fallando | 500 no manejado (incluso por DB caída: esa caída ya pagina como CRITICAL una sola vez por `database`); auth sin veredicto; fallo de etapa del borrado de cuenta; falla de entrega de soporte; job falló; ninguna sincronización de correo en 24 h |
| CRITICAL | Caída general, seguridad, integridad | DB inaccesible o sin conexiones; pico de 5xx; SMTP rechaza credenciales; presupuesto de alertas agotado |

Por defecto se envía a Discord desde **ERROR** (`OPS_ALERT_MIN_SEVERITY`). Los WARNING repetidos escalan solos: 5 fallas de sincronización de correo en 10 min pasan a ERROR, y 10 requests lentos también.

---

## 4. Matriz

| Componente | Qué observamos | WARNING | ERROR / CRITICAL | Alerta |
|---|---|---|---|---|
| API | 500 no manejados, 5xx deliberados, latencia, pico de 5xx | 503 deliberado (nunca cuenta para el pico); request > 5 s (escala por ruta) | 500 = ERROR; ≥20 500 reales en 5 min = CRITICAL | ERROR+ |
| Base de datos | Conexión nueva falla (red, sin slots de Supavisor); sonda de readiness | — | CRITICAL | Sí; `unreachable` se recupera con la sonda, `connect_failed` tras 15 min sin fallas |
| Auth / Supabase | Autenticación sin veredicto (Supabase o DB caídos → 503 a la app) | — | ERROR | Sí |
| Gmail / Outlook | Fallas de sincronización por proveedor y por disparador; mantenimiento sin completar; ninguna sincronización en 24 h | 1 falla de proveedor | 5 en 10 min = ERROR; todas las conexiones fallaron = ERROR; sin sincronizar 24 h = ERROR | ERROR+ |
| Tiendas (Apple/Google) | Lectura/reconocimiento de Google falló; cron de vencimientos | — | ERROR | Sí |
| Soporte | Entrega por email o Discord falló; SMTP sin credenciales | — | ERROR / CRITICAL | Sí (el de Discord solo en logs si Discord mismo falla) |
| Borrado de cuenta | Etapa falló (con nombre de etapa); tombstone pendiente | tombstone | ERROR | Sí |
| Jobs | Heartbeat de notificaciones, vencimientos de tiendas, mantenimiento Gmail e IBKR; notificaciones trabadas > 1 h | trabadas | falla del job = ERROR | Sí, y RECOVERED en la siguiente corrida buena |
| Deploys | Fallo informado por GitHub/Render/Vercel | — | ERROR | Sí (además del Web Push existente) |
| Uptime | `/health/ready` desde afuera | — | DOWN = CRITICAL | DOWN, recordatorio cada hora, RECOVERED |
| Cliente | Incidentes que reporta la app (sistema existente) | — | según `_incident_severity` | Canal existente |

---

## 5. Cómo leer una alerta

```
DINCR OPS · ERROR · CONTINÚA
Entorno: render
Componente: api
Evento: server_error
Ruta: PUT /user-product/free/movements/{movement_id}
HTTP: 500
Error: OperationalError 57014
Ocurrencias: 47 en 10 min
Primera vez: hace 12 min
Request ID: 3f9c...
Huella: 53e5d23a51b8f446 · 2026-09-29 03:02:11 UTC
```

- **Título**: `ERROR` es la primera vez; `CONTINÚA` es el resumen al terminar el cooldown; `ESCALÓ` indica que subió la severidad; `RECOVERED` indica 15 minutos sin ocurrencias o que la sonda volvió a pasar; `DEMASIADAS ALERTAS` indica que se agotó el presupuesto.
- **Request ID**: es el de la última ocurrencia antes de la alerta. Se busca en los logs de Render (`dincr.access`, `dincr.ops`, `jarvis.api`). El usuario lo ve en la cabecera `X-Request-ID` y en el cuerpo de un 500 (`error_id`).
- **Huella**: identifica el incidente. Se busca en `/product-ops/owner/observability` y en `dincr.ops`.

## 6. Deduplicación, cooldown y recuperación

- **Huella** = componente + evento + ruta (plantilla, sin IDs) + estado HTTP exacto + clase de error + código. No incluye usuario, request ID ni latencia.
- **Primera ocurrencia**: alerta inmediata.
- **Durante el cooldown** (10 min): solo se cuenta.
- **Al terminar el cooldown**, si hubo más ocurrencias: un resumen "N ocurrencias en M min".
- **Si sube la severidad**: se alerta de inmediato.
- **Presupuesto global**: 12 alertas cada 10 min. Pasado eso se envía un solo aviso de "DEMASIADAS ALERTAS" por ventana. Todo sigue quedando en los logs.
- **Recuperación**: `database.unreachable` se recupera cuando la sonda vuelve a pasar; un job, en su siguiente corrida exitosa; el resto (incluido `database.connect_failed`), tras 15 min sin ocurrencias.
- El estado vive **en memoria del proceso**, a propósito: así funciona aunque la DB esté caída. Con N procesos, un incidente puede alertar hasta N veces por cooldown. Un reinicio olvida el estado; como mucho se reenvía una alerta.

## 7. Salud

| Endpoint | Acceso | Qué hace |
|---|---|---|
| `GET /health/live` | Público | `{"status":"alive"}`. No toca nada. Para el health check de Render |
| `GET /health/ready` | Público | `healthy` / `degraded` (200) o `unhealthy` (503) con `{"checks":{"database":"ok|fail"}}` |
| `GET /product-ops/owner/observability` | Owner | Incidentes abiertos, heartbeats de jobs, configuración de alertas (nunca el webhook) y contadores de conexiones |
| `GET /product-ops/health` | Con sesión | Sin cambios: salud según los incidentes de clientes |

Detalles de `/health/ready`:
- Usa una conexión propia con timeout de 3 s; nunca la del pool de requests.
- El resultado, bueno o malo, se comparte 10 s, así que una avalancha de sondeos no se convierte en una avalancha de conexiones.
- `degraded` significa que la DB responde pero hay incidentes ERROR/CRITICAL abiertos en API, DB o auth. Jobs, integraciones y deploys no cambian el estado público.
- Mientras una sonda corre, las demás solicitudes responden con el último resultado; nunca esperan. La consulta tiene un límite de 2 s.
- `/health/live` corre en el event loop y no pasa por el pool de hilos: responde aunque todos los hilos estén ocupados.
- No expone host, DSN, versiones ni errores.

## 8. Privacidad

- Quien llama a `report()` pasa categorías y códigos, **nunca** payloads.
- Aun así, todo texto pasa por `sanitize_text`. Se eliminan:
  - `Bearer`, JWT y pares `token=` / `password=` / `secret=` / `code=` / `key=`…;
  - credenciales dentro de URLs y query strings;
  - emails;
  - claves con formato conocido (`ghp_`, `sk_`, `AKIA`, `AIza`…) y cadenas largas;
  - números de 6+ dígitos (cuentas, tarjetas, montos);
  - caracteres de control y saltos de línea (evita inyección en logs);
  - `` ` `` y `@` (evita escapar el bloque de código de Discord y las menciones).
- Discord siempre se llama con `allowed_mentions.parse = []`. Solo se menciona el rol configurado, y solo en CRITICAL.
- Una falla al enviar a Discord registra solo el tipo de error: el mensaje de conexión contiene la URL del webhook, que es su secreto.
- Nunca se registran cuerpos de request/response, cabeceras, cookies, SQL, contenido de correos, recibos ni montos.
- Las rutas se registran como plantilla (`/movements/{movement_id}`).

## 9. Qué NO se monitorea

- Un cliente que corta la conexión a mitad de un request (`ClientDisconnect`): se registra como info; no es una falla del servidor.

- Contenido de correos, montos y cualquier dato financiero: por diseño.
- Métricas de latencia por percentil (p95/p99) y series de tiempo: no hay backend de métricas.
- El frontend web o móvil, más allá de lo que ya existe: error boundary, handlers globales e incidentes de API.
- Vercel y Cloudflare: la landing es estática; sus builds ya se ven en GitHub.
- El número de conexiones de Supavisor: no está expuesto; se ve indirectamente en los fallos de conexión.
- Rate limiting: no existe en el backend.

## 10. "Algo está fallando a las 3:00 AM". ¿Qué hago?

1. **Mirá el título de la alerta.**
   - `UPTIME · DOWN`: el backend no responde; seguí con el paso 2.
   - `database`: seguí con el paso 3.
   - Otra: seguí con el paso 4.
2. **Backend caído:**
   - Revisá el estado del servicio en Render (deploy fallido, crash loop, plan o límite).
   - Mirá el último deploy: GitHub → Actions o Render → Events. Si coincide con la caída, hacé rollback en Render (Manual Deploy → commit anterior).
3. **Base de datos:**
   - Revisá el estado de Supabase (dashboard del proyecto y status.supabase.com).
   - `connect_failed` con muchas ocurrencias puede significar que Supavisor se quedó sin slots. Mirá el tráfico y los procesos en Render.
4. **Otras alertas:**
   - Copiá la **huella** y el **request ID**. En los logs de Render, filtrá por el request ID para ver la línea de `dincr.access` (ruta, estado, duración) y la de `jarvis.api` (resumen del error).
   - Abrí `/product-ops/owner/observability` para ver cuántas ocurrencias hay, desde cuándo, y los heartbeats de los jobs.
   - Si la falla es en correo o tiendas, revisá el proveedor (Google Cloud, App Store Connect). Si es un job, revisá el programador externo que llama al cron.
5. **Contener sin deploy:** apagá la función afectada desde el panel Owner (feature flags: `gmail_automation`, `financial_writes`, `store_billing`). La app le muestra al usuario un mensaje de mantenimiento.
6. **Cuando se resuelva:** esperá el `RECOVERED`, que llega solo.

## 11. Configuración

Todo está apagado por defecto. Nada cambia en producción hasta que el Owner lo active. Los valores son los de `backend/.env.example`.

| Variable | Default | Uso |
|---|---|---|
| `OPS_ALERTS_ENABLED` | vacío (apagado) | `true` activa el envío a Discord. Sin esto, solo hay logs |
| `OPS_DISCORD_WEBHOOK_URL` | vacío → usa `SUPPORT_DISCORD_WEBHOOK_URL` | Canal aparte, opcional |
| `OPS_ALERT_MIN_SEVERITY` | `error` | `info` / `warning` / `error` / `critical` |
| `OPS_ALERT_COOLDOWN_SECONDS`, `OPS_ALERT_RECOVERY_SECONDS` | 600 / 900 | Cooldown / silencio necesario para RECOVERED |
| `OPS_ALERT_BUDGET`, `OPS_ALERT_BUDGET_WINDOW_SECONDS` | 12 / 600 | Presupuesto global |
| `OPS_5XX_SPIKE_THRESHOLD` | 20 | 5xx en 5 min que disparan el pico |
| `OPS_SLOW_REQUEST_MS` | 5000 | Umbral de request lento |
| `OPS_MAIL_SYNC_STALE_HOURS` | 24 | Horas sin sincronizar para `mail_sync_stale` |
| `DINCR_ENVIRONMENT` | `render` / `local` | Etiqueta de entorno |
| `SUPPORT_DISCORD_ALERT_ROLE_ID` | existente | Rol a mencionar en CRITICAL |

Uptime (GitHub → Settings → Secrets and variables → Actions):
- variable `DINCR_UPTIME_URL`: la URL base del backend, sin ruta;
- secret `OPS_UPTIME_DISCORD_WEBHOOK_URL`: puede ser el mismo webhook de operaciones.

Opcional: en Render → Settings → Health Check Path, usar `/health/live`. No uses `/health/ready`: Render reiniciaría el servicio cada vez que la DB falle.

## 12. Cómo probarlo

- **Tests:** `python -m pytest backend/tests/test_observability.py -q`.
- **Canal de Discord:** `POST /product-ops/owner/support/discord/test` (existente, Owner).
- **Sonda externa:** GitHub → Actions → Uptime → Run workflow. Con la URL mal configurada a propósito, tiene que llegar un DOWN; al corregirla, un RECOVERED.
- **Salud:**
  - `curl https://<backend>/health/live`
  - `curl -i https://<backend>/health/ready`

## 13. Limitaciones

- `sanitize_text` es una red de seguridad, no un permiso: a `report()` solo llegan tipos, códigos y etapas. No redacta valores con espacios (`password: dos palabras`), montos de 5 dígitos ni separadores `/` o `_` en tarjetas. Redacta de más: cualquier `algo_key=`, `algo_code=` o `algo_token=`.
- Un 500 que escapa sin manejar no deja una línea en `dincr.access`: el log de error (`jarvis.api`) y `dincr.ops` sí la tienen.
- Un borrado de cuenta que falla con 500 alerta dos veces: por `account_deletion` y por `api`.

- El estado de deduplicación es por proceso y se pierde al reiniciar (ver §6).
- La sonda externa depende de GitHub Actions: los cron programados pueden atrasarse varios minutos, y un repo sin actividad durante 60 días desactiva los schedules.
- Si Discord está caído, las alertas quedan en los logs y en la vista Owner, pero no llegan.
- `slow_request` excluye los endpoints batch (`/cron`, `/sync`, `/maintenance`, `/push`, `/callback`, `/snapshot`).
- Los heartbeats de jobs viven en memoria. La detección de "job que dejó de correr" usa el estado de la DB (correo y notificaciones); los crons de tiendas e IBKR no tienen un indicador persistente de última corrida.

## 14. Mejoras futuras (no instaladas)

| Opción | Qué resolvería | Cuándo tiene sentido | Costo aprox. |
|---|---|---|---|
| Sentry (errores backend + app) | Stack traces agrupados, releases, sesiones afectadas | Cuando haya volumen de usuarios y un equipo que triage errores a diario | Plan Developer gratis (1 usuario, 5k errores/mes); Team ≈ USD 26/mes |
| Better Stack / UptimeRobot | Uptime cada 1–5 min con historial y página de estado, sin depender de GitHub | Si los retrasos de GitHub Actions molestan, o para una página de estado pública | Gratis en planes básicos (5 min); pagos desde ≈ USD 7–25/mes |
| Log drain de Render → Better Stack / Grafana Loki | Búsqueda y retención de logs, alertas por consulta | Cuando buscar en los logs de Render no alcance | Planes gratuitos limitados; pagos ≈ USD 10–30/mes |
| Métricas (Prometheus/Grafana Cloud) | p95/p99, tasas y tableros | Cuando haya SLOs formales | Grafana Cloud free tier |

No se instaló ninguna. Todo lo anterior reemplazaría o complementaría piezas de este sistema, sin cambiar la forma en que se llama a `report()`.
