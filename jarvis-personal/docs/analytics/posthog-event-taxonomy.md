# DINCR: analítica de producto con PostHog

> **Regla permanente: la analítica observa el comportamiento del producto, no el contenido financiero del usuario.**

PostHog es la telemetría permanente de DINCR. Sirve para saber cómo funciona el producto después del lanzamiento sin revisar la base de datos. Recibe eventos, estados, resultados, conteos, duraciones y metadata técnica no sensible. **Nunca** es una copia de Supabase.

## 1. Arquitectura

| Capa | Archivo | Qué hace |
|---|---|---|
| Contrato del móvil | `frontend/src/lib/analyticsContract.js` | Lista cerrada de eventos y propiedades. `safeAnalyticsProperties` descarta todo lo demás y `endpointModule` convierte una ruta de API en un módulo fijo. |
| SDK del móvil | `frontend/src/lib/productAnalytics.js` | `posthog-js`, **solo en la compilación nativa DINCR**, solo para cuentas Users (Free, Basic, VIP) con los documentos legales aceptados. `before_send` reconstruye cada evento con la lista cerrada. |
| Fachada | `frontend/src/lib/telemetry.js` (`trackEvent`, `trackScreen`, `recordError`) | Único punto de emisión, **solo hacia PostHog**. Firebase no recibe nada. |
| Contrato del servidor | `backend/product_ops/posthog_events.py` | `SERVER_EVENTS` define, para cada evento, sus propiedades y tipos cerrados. `capture_backend_event` se usa desde `BackgroundTasks`; `capture_backend_event_later` es una cola en un hilo, no bloqueante, para syncs, crons y handlers. |
| Salud de la sincronización de correo | `backend/user_product/mail_sync_analytics.py` | Un solo resultado por cada sync de Gmail/Outlook, con todos sus disparadores (manual, conexión, mantenimiento, push). |
| Baseline histórico | `backend/scripts/posthog_signups_baseline.py` | Se corre una sola vez, a mano: agregados diarios de altas. |

- **Identidad.**
  - En el móvil, PostHog usa un **ID anónimo de dispositivo**, que se rota al cerrar sesión o cambiar de cuenta. No se llama a `identify`, no se crean perfiles de persona (`person_profiles: "never"`, `$process_person_profile: false`), no hay geolocalización por IP y no se envían ID de cuenta ni de workspace.
  - Los eventos del servidor usan un `distinct_id` aleatorio **nuevo por evento**: son contadores agregados.
- **Por qué no un pseudónimo estable de cuenta.** La Política de Privacidad publicada describe la analítica de PostHog como *anónima*. Un pseudónimo estable (por ejemplo, un HMAC del `account_id`) daría retención más exacta entre dispositivos, pero es un dato personal seudonimizado y exige cambiar primero el texto legal. **HUMAN GATE**: decisión legal o de producto. Hasta entonces, DAU/WAU/MAU y la retención se cuentan por dispositivo; reinstalar la app o usar dos teléfonos infla levemente las cifras.
- **Owner.**
  - No emite eventos de cliente: es uso interno y contaminaría las métricas del producto.
  - Los eventos de servidor (sync, errores) son anónimos para todos, el Owner incluido. Siguen exactamente las mismas reglas de privacidad.
- **Replay y otros:** autocapture, pageviews automáticas, session replay, excepciones con stack, encuestas y feature flags remotos están **desactivados**. El replay no vuelve a activarse: capturaría montos y datos financieros en pantalla.

## 2. Eventos

### Móvil (en tiempo real)

**Ciclo de vida**

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `app_opened` | Primera vez que una cuenta elegible abre la app en la sesión | — |
| `app_resumed` | La app vuelve a primer plano | — |
| `login_completed` | Un inicio de sesión real (no una sesión restaurada), una vez por login | — |
| `logout` | Cierre de sesión, enviado antes de rotar el ID anónimo | — |
| `onboarding_started` / `onboarding_completed` | Inicio y fin del onboarding | — |
| `screen_viewed` | Cambio de módulo | `screen`: lista cerrada de módulos |
| `account_deletion_started` / `account_deletion_failed` | Eliminación de cuenta | — |
| `data_export_completed` | Exportación de datos | — |

**Planes**

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `plan_selected` | El usuario elige un plan | `plan` |
| `plan_access_granted` | Se otorga acceso al plan | `access_type`: free/promotion |

**Correo**

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `gmail_connection_started` | Se abre el consentimiento del proveedor (Gmail u Outlook) | `provider`, `source_type` |
| `mail_connected` | Outlook conectado (Gmail se cuenta en el servidor) | `provider` |
| `mailbox_connection_failed` | El OAuth volvió con error | `provider`, `error_code`: lista cerrada |
| `gmail_sync_started` / `gmail_sync_completed` / `gmail_sync_failed` | "Actualizar" manual desde la pantalla | `scan_scope`, `initial_scan_complete`, `success`, `messages_scanned`, `candidates_pending`, `duplicates` |
| `gmail_disconnected` | Buzón desconectado | — |
| `email_candidate_reviewed` / `transaction_candidate_reviewed` | Revisión de un candidato | `source_type`, `decision` |
| `transaction_confirmed` / `transaction_rejected` | Resultado de la revisión | `source_type` |
| `financial_account_confirmed` / `financial_account_ownership_reviewed` | Revisión de cuentas | `ownership_status` |

**Errores**

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `api_error` | Una llamada a la API falló (misma deduplicación de 15 min que el reporte de incidentes) | `endpoint` (módulo, nunca la ruta), `method`, `status_code`, `error_category` |
| `app_error` | Error JavaScript no manejado | `error_category` (sin mensaje ni stack) |

- **Propiedades comunes**, que el SDK agrega a cada evento: `plan`, `platform` (android/ios), `app_version`, `environment` (production/staging/development).
- **`financial_account_detected`:** está reservado en el contrato, pero no se emite.

### Servidor (en tiempo real, anónimos)

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `gmail_connected` | La sesión que inició el flujo completa la vinculación de Gmail | — |
| `account_deletion_completed` | Después de una eliminación exitosa | — |
| `mail_sync_completed` | Cada sync de Gmail/Outlook con cualquier disparador | `provider`, `trigger` (manual/connect/maintenance/push), `scan_scope`, `initial_scan_complete`, `duration_ms`, `messages_scanned`, `candidates_pending`, `duplicates`, `payroll_reports`, `messages_failed` (avisos que no se pudieron procesar) |
| `mail_sync_failed` | Una sync falló | `provider`, `trigger`, `error_code` (reauth_required/access_denied/provider_error), `duration_ms` |
| `server_error` | Una respuesta 5xx | `route` (plantilla de código, sin IDs), `method`, `status_code`, `exception_type` (clase, sin mensaje) |
| `subscription_changed` | Motor de suscripciones (sandbox, Apple o Google) | `plan`, `billing_period`, `subscription_event`, `store` |
| `baseline_daily_signups` | Solo con el backfill manual | `count` |

Todos los eventos del servidor llevan además `success`, `source_type=server`, `environment`, `$process_person_profile=false` y `$geoip_disable=true`.

### Correspondencia con los nombres pedidos

Los nombres existentes se conservan por compatibilidad con los datos ya recolectados.

| Nombre pedido | Evento DINCR |
|---|---|
| `mailbox_connection_started` | `gmail_connection_started` (con `provider`) |
| `mailbox_connected` | `gmail_connected` (servidor) + `mail_connected` (Outlook) |
| `mailbox_connection_failed` | `mailbox_connection_failed` |
| `mailbox_disconnected` | `gmail_disconnected` |
| `mail_sync_started/completed/failed` | `mail_sync_completed/failed` (servidor, fuente de verdad de la salud); `gmail_sync_*` (móvil, uso de la UI) |
| `messages_scanned_count`, `candidates_created_count` | propiedades `messages_scanned` y `candidates_pending` de `mail_sync_completed` |
| `candidates_confirmed/rejected_count` | `transaction_confirmed` / `transaction_rejected` (contar eventos) |
| `parser_success` / `parser_failure` | `mail_sync_completed` vs `mail_sync_failed` + `messages_scanned` y `candidates_pending` por sync |
| `upgrade_*` | `plan_selected` → `plan_access_granted` y `subscription_changed` (`purchased`/`upgrade`) |
| `subscription_cancelled` | `subscription_changed` (`cancel_requested`/`expired`/`revoked`) |
| `account_deleted` | `account_deletion_completed` |

**No se miden, a propósito:**
- `signup_started`, `login_failed` y `plan_viewed` antes de aceptar los documentos legales. No se envía nada antes de ese consentimiento. `plan_viewed` equivale a `screen_viewed` con `screen=plan` después de la aceptación.
- `unsupported_sender_detected` y `parser` por banco: exigirían una propiedad por mensaje. Hoy basta con los conteos por sync. Agregar un identificador de banco (lista cerrada `bac/popular/multimoney`) es posible como cambio aparte.

## 3. Propiedades

- **Permitidas:** solo las de las tablas anteriores, con valores de listas cerradas, enteros acotados, booleanos, `app_version` numérica, `duration_ms` redondeada y `status_code` entre 100 y 599. En el servidor además se aceptan plantillas de ruta y nombres de clase de excepción.
- **Prohibidas siempre:**
  - contenido de correos (subject, body, snippet, remitente, adjuntos);
  - PDFs y documentos;
  - movimientos, montos, saldos, salarios, deudas;
  - números de cuenta, IBAN, tarjetas, SINPE, contrapartes;
  - `raw_payload`;
  - tokens OAuth, access/refresh tokens, cookies, headers de autorización, contraseñas, secretos;
  - correo, nombre, teléfono, IP;
  - ID de cuenta, workspace, usuario o buzón;
  - URLs y rutas con parámetros;
  - mensajes o stacks de error.

## 4. Cómo agregar un evento

1. Confirmá que responde una pregunta de producto, salud o conversión, no un clic sin valor.
2. **Móvil:** agregalo a `analyticsEvents` en `analyticsContract.js`. Si necesita una propiedad nueva, agregala a `categories` (lista cerrada), a `counts` o a `booleans`. Emitilo con `trackEvent("nombre", {...})`.
3. **Servidor:** agregalo a `SERVER_EVENTS`, con sus propiedades y tipos en `ENUMS`, `COUNTS` o `BOOLEANS`. Emitilo con `capture_backend_event_later("nombre", {...})` o, dentro de un request, con `BackgroundTasks.add_task(capture_backend_event, "nombre", {...})`.
4. **Probalo:**
   - `npm run test:product-analytics`: contrato, guard de nombres sensibles, escaneo estático de cada `trackEvent` y pipeline real de posthog-js.
   - `python -m pytest backend/product_ops/test_analytics_privacy_contract.py`: guard de nombres, valores hostiles, escaneo AST de cada llamada de captura, anonimato, desactivación, fallas, entornos, un solo evento por sync.
5. Documentalo en este archivo.

Los guards fallan si un evento no está en el contrato, si una propiedad permitida tiene un nombre sensible (`amount`, `email`, `token`, `subject`…) o si una llamada envía una clave fuera del contrato.

## 5. Variables de entorno

| Dónde | Variable | Valor |
|---|---|---|
| Build móvil (Android/iOS) | `VITE_POSTHOG_KEY` | **Project API key** del proyecto *DINCR Production*. Nunca una personal/admin key. |
| Build móvil | `VITE_POSTHOG_HOST` | `https://us.i.posthog.com` (región US del proyecto) |
| Build móvil | `VITE_ANALYTICS_ENVIRONMENT` | `production`, o `staging` para builds de prueba (por defecto `production` en builds de release) |
| Render (backend) | `POSTHOG_API_KEY` | La misma Project API key |
| Render | `POSTHOG_HOST` | El mismo host |
| Render | `ANALYTICS_ENVIRONMENT` | Opcional (por defecto `production` en Render, `development` fuera) |

Sin clave o con un host fuera de la lista (`us|eu.i.posthog.com`), la analítica queda **apagada**: no se inicializa nada, no se encola nada y no se envía nada.

## 6. Si PostHog falla

- **Móvil:** cada llamada va envuelta en `try/catch`; la app nunca espera a PostHog.
- **Servidor:** timeout de 0,5 s para conectar y 1,5 s para leer. Los eventos de syncs y errores se encolan en un hilo, así que el request o el cron no esperan. Una falla solo deja un warning en el log, sin datos.
- **Pérdidas posibles:** se pierden los eventos de ese momento y nada más.

## 7. Dashboards

Todos se calculan desde los eventos: **no hay crons de snapshots**. Diario, semanal y mensual son ventanas de PostHog sobre los mismos eventos. Filtro global en todos: `environment = production`.

1. **DINCR — Executive** (mensual):
   - MAU: usuarios únicos de `app_opened`, mensual;
   - crecimiento de MAU;
   - nuevos dispositivos (lifecycle de `app_opened`);
   - retención a 30 días;
   - conversión por plan (`plan_selected` desglosado por `plan`);
   - cancelaciones (`subscription_changed` con `subscription_event` en cancel_requested/expired/revoked);
   - adopción (`screen_viewed` por `screen`);
   - fiabilidad (`server_error` y `api_error` por semana).
2. **DINCR — Activation & Retention** (semanal):
   - DAU/WAU/MAU;
   - embudo `app_opened` → `onboarding_started` → `onboarding_completed`;
   - activos por `plan`;
   - retención 1/7/30 días (`app_opened` → `app_opened`/`app_resumed`);
   - stickiness;
   - adopción por módulo (`screen_viewed` por `screen`).
3. **DINCR — Mail Automation**:
   - embudo `gmail_connection_started` → `gmail_connected`/`mail_connected`;
   - fallos por `error_code` y `provider`;
   - Gmail vs Outlook;
   - tasa de éxito (`mail_sync_completed` / (`completed` + `failed`), por `provider` y `trigger`);
   - p50/p90 de `duration_ms`;
   - suma de `messages_scanned` y `candidates_pending` por día;
   - tasa de confirmación: `transaction_confirmed` / (`transaction_confirmed` + `transaction_rejected`);
   - `reauth_required` por semana.
4. **DINCR — Reliability**:
   - `server_error` por `route` y `status_code`;
   - `api_error` por `endpoint`, `status_code` y `app_version`;
   - `app_error` por `app_version` y `platform`;
   - errores por cada 100 sesiones (`api_error` / `app_opened`) por `app_version`;
   - sesiones sin error: dispositivos con `app_opened` sin `app_error` ese día.
5. **DINCR — Plans & Conversion**:
   - embudo Free → `plan_selected` (basic/vip) → `plan_access_granted` → `subscription_changed` (purchased/upgrade);
   - `subscription_changed` por `subscription_event` y `store`;
   - activos por plan.

**Estado:** no se crearon automáticamente. El conector PostHog está conectado al proyecto *DINCR Production*, pero el modo automático bloqueó su uso en esta sesión. Kenneth puede crearlos con esta definición o autorizar el conector.

## 8. Alertas (PostHog Insight alerts sobre los trends anteriores)

| Alerta | Condición | Ruido evitado |
|---|---|---|
| Aumento de errores del servidor | `server_error` diario > 3× el promedio de 7 días **y** ≥ 20 | Umbral absoluto mínimo |
| Fallos de sync | `mail_sync_failed` / total de syncs > 20 % en el día **y** ≥ 10 fallos | Mínimo de volumen |
| Reautorizaciones | `mail_sync_failed` con `error_code=reauth_required` > 10/día | — |
| Caída de actividad | DAU < 50 % de la media de 7 días | Se evalúa una vez al día |
| Nueva versión | `api_error` + `app_error` por `app_version` nueva > 2× la versión anterior en 24 h | Comparación relativa |

Si el plan de PostHog no soporta alguna condición compuesta, usar la alerta de umbral simple más cercana y revisarla en el dashboard Reliability. No se construye infraestructura nueva.

## 9. Datos históricos

- **Sí:** altas por día (`accounts.created_at`, excluido el Owner) mediante `backend/scripts/posthog_signups_baseline.py`.
  - Por defecto hace un dry run, solo lee y envía únicamente agregados diarios.
  - Es idempotente: usa `uuid` y `timestamp` deterministas.
  - Se ejecuta **una sola vez**, a mano.
  - Límite: las cuentas eliminadas antes del backfill no cuentan.
- **No:**
  - actividad pasada: que una cuenta exista no prueba que estuviera activa;
  - plan al momento del alta;
  - historial de buzones: `connected_at` cambia con cada reconexión;
  - resultados de syncs.
  Todo eso empieza a medirse desde el release.

## 10. Privacidad y gates humanos

- **Antes de distribuir un build con `VITE_POSTHOG_KEY`:**
  1. PostHog → Project settings → **Discard client IP data** activado.
  2. La Política de Privacidad publicada ya nombra a PostHog (analítica de producto anónima, sin correo, nombre ni datos financieros). Cualquier cambio a pseudónimos estables exige una versión legal nueva.
- **Firebase:** solo distribuye builds de prueba (App Distribution). No hay SDK de Firebase, Analytics ni Crashlytics en la app, y no recibe ningún dato del usuario (ver `docs/android-local-build.md`). Un fallo de render de React se reporta en PostHog como `app_error` con `error_category=render_error`, sin mensaje ni stack.

## 11. Verificación física mínima (teléfono → PostHog)

1. Compilar con `VITE_POSTHOG_KEY`/`VITE_POSTHOG_HOST` e instalar en Android e iOS.
2. Entrar con una cuenta User que ya aceptó los documentos legales. En Activity/Live events deben aparecer:
   - `app_opened`, y `login_completed` si fue un login nuevo;
   - `screen_viewed` al navegar;
   - `app_resumed`;
   - `logout`.
3. Abrir un evento. Debe tener solo `plan`, `platform`, `app_version`, `environment`, `screen` o las propiedades de su tabla, más `token`, `distinct_id`, `$process_person_profile=false` y `$geoip_disable=true`. No debe tener URL, correo, banco, montos, IDs ni `$set`.
4. **Persons:** no debe haber perfiles nuevos.
5. **Correo:**
   - conectar Gmail: `gmail_connection_started`, un único `gmail_connected` (servidor) y `mail_sync_completed` (`trigger=connect`);
   - cancelar un consentimiento: `mailbox_connection_failed` con `error_code=denied`.
6. **Owner** y cuenta sin aceptación legal: ningún evento de cliente.
7. **Red:** solo `/e/` y `/array/<key>/config`; nada de `/flags` ni scripts externos.
