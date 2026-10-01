# DINCR: analítica de producto con PostHog

> **Regla permanente: la analítica observa el comportamiento del producto, no el contenido financiero del usuario.**

PostHog es la telemetría permanente de DINCR. Sirve para saber cómo funciona el producto después del lanzamiento sin revisar la base de datos. Recibe eventos, estados, resultados, conteos, duraciones y metadata técnica no sensible. **Nunca** es una copia de Supabase.

Este documento es el **contrato v2**: taxonomía canónica, audiencias Users/Owner, identidad, allowlist de propiedades y configuración de build. Es **un solo contrato** para todos los clientes: la app Capacitor y las apps nativas iOS/Android.

## 1. Arquitectura

| Capa | Archivo | Qué hace |
|---|---|---|
| Contrato del móvil | `frontend/src/lib/analyticsContract.js` | Listas cerradas de eventos (`userEvents`, `ownerEvents`) y de propiedades. `safeAnalyticsProperties` descarta todo lo demás. `endpointModule`, `usefulActionFor` y `reviewLatencyBucket` convierten datos locales en categorías fijas. |
| SDK del móvil | `frontend/src/lib/productAnalytics.js` | `posthog-js`, **solo en la compilación nativa DINCR** (Capacitor `com.dincr.app`). Decide la audiencia de la cuenta (`user`, `owner` o ninguna). `before_send` reconstruye cada evento con la lista cerrada. |
| Fachada | `frontend/src/lib/telemetry.js` (`trackEvent`, `trackScreen`, `recordError`) | Único punto de emisión. Las páginas `jarvis_*` del Owner se envían como `jarvis_section_viewed`. |
| Acción útil | `frontend/src/users/services/jarvisApi.js` (`request`) | Tras una escritura exitosa de Users, emite `useful_action` con el tipo de acción (nunca la ruta ni el contenido). |
| Relay de las apps nativas | `backend/product_ops/analytics_relay.py` (`POST /product-ops/analytics`) | Recibe los eventos v2 de iOS/Android y los valida contra el mismo contrato (paridad probada). Decide en el servidor la audiencia, el plan y el entorno, y los reenvía a PostHog con la configuración existente del backend. No escribe en la base de datos. |
| Contrato nativo | `native/android/core/data/.../Analytics.kt`, `native/ios/DincrKit/Sources/DincrCore/Analytics.swift` | Eventos que envía la app nativa, mapeo de pantallas, reglas de acción útil (idénticas a las de Capacitor) e ID anónimo de instalación. Sin SDK ni clave de PostHog. |
| Contrato del servidor | `backend/product_ops/posthog_events.py` | `SERVER_EVENTS` define, por evento, sus propiedades y tipos cerrados. |
| Salud de la sincronización de correo | `backend/user_product/mail_sync_analytics.py` | Un resultado por cada sync de Gmail/Outlook, con todos sus disparadores. |
| Baseline histórico | `backend/scripts/posthog_signups_baseline.py` | Se corre una sola vez, a mano: agregados diarios de altas. |

**Clientes y transporte:**

| Cliente | Estado | Cómo llega a PostHog |
|---|---|---|
| Capacitor (`frontend/`), Android e iOS | App de tienda actual. Sigue siendo el **fallback** mientras termina la migración | `posthog-js` en el dispositivo, con `client=capacitor`. Necesita `VITE_POSTHOG_KEY` y `VITE_POSTHOG_HOST` en el build (§7) |
| Nativa iOS (Swift) y Android (Kotlin) (`native/`) | **Candidata de reemplazo**, con la identidad de release `com.dincr.app`. Sustituir Capacitor está sujeto a los gates humanos de `native/RELEASE_IDENTITY.md` | `POST /product-ops/analytics` → validación y allowlist en el backend → PostHog, con `client=native`. **Sin SDK ni clave de PostHog en el cliente.** Usa la configuración de PostHog que el backend ya tiene |
| Web y dincr.com | — | Nada |

- **Por qué un relay y no el SDK en Swift/Kotlin:**
  - un solo contrato validado en el servidor;
  - ningún SDK, secreto ni configuración nueva en cada cliente;
  - la audiencia y el plan salen de los registros del servidor, no del dispositivo;
  - PostHog ve la IP de Render, no la del usuario.
- **El relay no reemplaza `POST /product-ops/events`.** Ese endpoint sigue alimentando la tabla propia `product_events` (`*_opened`, con `account_id`), que usa el tablero interno de Product Ops. No se copia a PostHog.
- **Paridad garantizada** por `backend/product_ops/test_analytics_relay.py`:
  - el relay del backend replica el contrato de Capacitor (eventos y cada categoría);
  - Kotlin y Swift usan exactamente las mismas reglas de acción útil;
  - sus eventos, pantallas y secciones JARVIS pertenecen al contrato.

## 2. Audiencias: Users y Owner

| Audiencia | Quién | Qué puede enviar | Propiedades comunes |
|---|---|---|---|
| `user` | `role=user`, plan `free`/`basic`/`vip`, documentos legales aceptados | Solo `userEvents` | `audience`, `plan`, `platform`, `app_version`, `environment` |
| `owner` | `role=owner`, documentos legales aceptados | Solo `ownerEvents` (`jarvis_*`) | `audience`, `platform`, `app_version`, `environment` (sin `plan`) |
| ninguna | admin, cuentas sin aceptación legal, planes desconocidos, web, builds sin clave | Nada | — |

Todos los eventos llevan además `client`: `capacitor` o `native`.

**Quién decide la audiencia:**
- **Capacitor:** el SDK, con el perfil de `/auth/me`.
- **Nativo:** el **servidor** (`analytics_relay.audience_of`), con el rol, el plan y la aceptación legal de sus propios registros. El cliente no puede fijar `audience`, `plan`, `client` ni `environment`. Un build `debug` se etiqueta siempre `development`.

**Owner y aceptación legal (decidido).** El Owner **no** está exento: es una cuenta DINCR real y necesita la aceptación vigente, igual que Users. Sin ella no se envía **ningún** evento JARVIS (fail-safe).

**Gap conocido.** `App.jsx` salta la pantalla `LegalConsent` para los roles owner y admin, así que el Owner nunca puede registrar su aceptación desde la app. El backend ya calcula `legal` para cualquier rol y `POST /auth/legal/accept` acepta cualquier rol. El arreglo es solo de cliente y queda como follow-up aparte: mostrar `LegalConsent` al Owner cuando `legal.required` sea verdadero, sin volver a correr el onboarding.

La app nativa ya pide la aceptación al Owner (`IdentityGate.LEGAL_REQUIRED` antes de `READY`).

- La audiencia la decide la cuenta, nunca quien llama: `captureProductEvent` siempre sobrescribe `audience`.
- **Excluir al Owner de las métricas comerciales:** filtrar `audience = user`. Un evento de Users nunca lleva `audience=owner` y el Owner nunca emite eventos de Users. Lo prueba `npm run test:product-analytics`.
- **JARVIS:** solo metadata de navegación. **Nunca** texto del chat, prompts, eventos de calendario, nombres, montos, salario, datos bancarios ni información personal. Las propiedades son listas cerradas: no existe ninguna propiedad de texto libre.

## 3. Identidad

**Hoy (vigente):**
- **Móvil:** ID anónimo de dispositivo de posthog-js. Se rota al cerrar sesión o cambiar de cuenta. No se llama a `identify`, no hay perfiles de persona (`person_profiles: "never"`, `$process_person_profile: false`), no hay geolocalización por IP y no se envía ningún ID de cuenta.
  - PostHog deriva un `person_id` determinista del `distinct_id` aunque no haya perfiles. Por eso DAU/WAU/MAU, funnels y retención funcionan **por dispositivo**.
- **App nativa:** un UUID aleatorio por instalación (`analytics_install_id`), el equivalente nativo del ID anónimo de posthog-js.
  - Se rota al cerrar sesión.
  - Nunca se deriva de la cuenta, el correo ni ningún identificador.
  - El relay lo usa como `distinct_id` y no lo guarda, no lo registra en logs ni lo combina con `account_id` o `workspace_id`.
  - La sesión es un UUID que se renueva tras 30 minutos sin actividad.
- **Servidor:** un `distinct_id` aleatorio nuevo por evento (`dincr_server_<uuid>`). Sirve para conteos de salud, no para usuarios.

**Diseño propuesto: pseudónimo estable. NO implementado. HUMAN GATE legal.**

- **Por qué no se implementa:** la Política de Privacidad vigente (§5) describe PostHog como *"analítica de producto anónima"*. Un pseudónimo estable de cuenta es un dato personal seudonimizado, así que exige primero una versión legal nueva que lo declare. Hasta entonces, el contrato sigue anónimo por dispositivo.
- **El diseño, para cuando el gate se apruebe:**
  1. **Derivación:** solo en el servidor, `analytics_id = "u_" + base32(HMAC-SHA256(ANALYTICS_ID_SECRET, "dincr-analytics-v1:" + account_id))[:26]`.
     - Es estable para la misma cuenta y distinto entre cuentas.
     - No es reversible sin el secreto, que vive solo en el backend.
     - No usa correo, nombre, teléfono, ni identificadores bancarios o de tarjeta.
     - Rotar el secreto o el prefijo de versión corta toda la historia, a propósito.
  2. **Entrega:** `/auth/me` devuelve `analytics_id` solo si la cuenta es elegible (audiencia `user` u `owner`). Sin secreto configurado, el campo no existe y el cliente sigue anónimo (fail-safe).
  3. **Cliente:** `posthog.init(..., { bootstrap: { distinctID: analytics_id } })`. No se usa `identify` ni se crean perfiles (`person_profiles: "never"`) y no hay `$set`.
  4. **Servidor:** los eventos ligados a una acción del usuario (por ejemplo `mailbox_connected` del callback) usan el mismo `analytics_id`, calculado con la misma función. Eso permite funnels entre app y backend. Los eventos sin usuario (cron, push, `server_error`) siguen siendo anónimos.
  5. **Owner:** su ID usa el mismo esquema, pero sus eventos llevan siempre `audience=owner`. El Owner jamás comparte ID ni audiencia con Users.
  6. **Borrado de cuenta:** se borran las personas/eventos de ese `distinct_id` en PostHog (API de borrado). Esto se agrega al flujo de eliminación en el mismo cambio.
- **Prerrequisitos de producción:**
  - versión legal nueva publicada;
  - `ANALYTICS_ID_SECRET` en Render;
  - el cambio de código.
  Nada de esto está hecho.

## 4. Taxonomía canónica (contrato v2)

### Users (móvil)

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `app_opened` | Primera vez que una cuenta elegible abre la app en la sesión | — |
| `app_resumed` | La app vuelve a primer plano | — |
| `login_completed` | Inicio de sesión real (no una sesión restaurada) | — |
| `logout` | Cierre de sesión, antes de rotar el ID | — |
| `screen_viewed` | Cambio de módulo | `screen`: cada id de `products/finva/features/registry.jsx`, incluidos los `vip-*` |
| `strategy_tool_opened` | Se abre una herramienta de Estrategia | `strategy_tool`: salvavidas/investments/debts/distribution/aguinaldo |
| `onboarding_started` / `onboarding_completed` | Inicio y fin del onboarding (elección de plan) | — |
| `plan_selected` | El usuario elige un plan | `plan`, `plan_change`: immediate/scheduled/kept |
| `plan_access_granted` | Se otorga acceso al plan | `access_type`: free/promotion |
| `financial_profile_saved` | Se guardó la situación financiera (perfil) | — |
| `useful_action` | Una escritura exitosa hecha a propósito: actividad significativa | `action_type`: lista cerrada (ver `usefulActionTypes`) |
| `mailbox_connection_started` | Se abre el consentimiento del proveedor | `provider` |
| `mailbox_connected` | El OAuth volvió con éxito (Gmail u Outlook) | `provider` |
| `mailbox_connection_failed` | El OAuth volvió con error | `provider`, `error_code` |
| `mailbox_disconnected` | Buzón desconectado | — |
| `mail_sync_requested` | "Actualizar" manual. El resultado lo reporta el servidor | — |
| `mail_candidate_reviewed` | Revisión de un candidato | `decision`: accepted/corrected/rejected, `review_latency`: under_1h/under_1d/under_7d/over_7d, medido desde que DINCR **detectó** el candidato (no desde la fecha del correo) |
| `financial_account_reviewed` | Revisión de una cuenta detectada | `ownership_status`: own/not_mine |
| `account_deletion_started` / `account_deletion_failed` | Eliminación de cuenta | — |
| `data_export_completed` | Exportación de datos | — |
| `api_error` | Una llamada a la API falló (deduplicado 15 min) | `endpoint` (módulo), `method`, `status_code`, `error_category` |
| `app_error` | Error JavaScript no manejado o fallo de render | `error_category` |

### Owner (móvil, `audience=owner`)

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `jarvis_opened` | Capacitor: el Owner abre la app (una vez por sesión). Nativo: el Owner abre el hub JARVIS | — |
| `jarvis_section_viewed` | Cambio de sección de JARVIS | `jarvis_section`: cada página de `personal/PersonalApp.jsx` (por ejemplo `chats`) y cada `Jarvis.Section` nativa (`chat`, `calendar`, que es la Agenda, `memory`…). Es solo navegación: nunca su contenido |

**Pendiente** (decisión aparte, no implementado): `jarvis_intent_resolved` {`intent_category`: overtime/bonus/holiday_vgh/calendar/other, `status`: pending_confirmation/confirmed/cancelled, `success`}.
- Viviría en las apps nativas y viajaría por el mismo relay.
- Requiere definir antes cómo se clasifica un intent sin texto.

### Apps nativas (iOS/Android, por el relay)

Hoy envían este **subconjunto** del contrato. El relay acepta cualquier evento del contrato, así que agregar más no cambia el backend.

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `app_opened` | La identidad queda lista (una vez por sesión de la app) | — |
| `screen_viewed` | Android: pantallas que ya registraban `*_opened`. iOS: pestañas y Email Monitor | `screen`, mapeado con `AnalyticsContract.SCREENS` / `screens` (por ejemplo `home`→`overview`, `movements`→`transactions`) |
| `useful_action` / `financial_profile_saved` | Una escritura exitosa (gancho del cliente HTTP) | `action_type`, con las mismas reglas que Capacitor |
| `jarvis_opened` / `jarvis_section_viewed` | Owner: hub JARVIS y sus secciones | `jarvis_section` |

**Diferencias intencionales con Capacitor:**
- **Todavía no se instrumentan en nativo:** el funnel de onboarding (`onboarding_*`, `plan_selected`), el Email Monitor (`mailbox_*`, `mail_candidate_reviewed`), `strategy_tool_opened`, los errores cliente (`api_error`, `app_error`) y `login_completed`/`logout`. El contrato y el relay ya los aceptan; falta solo el punto de emisión en cada pantalla nativa.
- **`jarvis_opened`** significa "abrir el hub JARVIS" en nativo y "abrir la app" en Capacitor. Se distinguen con `client`.

### Servidor (anónimos)

| Evento | Cuándo | Propiedades adicionales |
|---|---|---|
| `gmail_connected` | El callback de Gmail completa la vinculación | — |
| `account_deletion_completed` | Después de una eliminación exitosa | — |
| `mail_sync_completed` | Cada sync de Gmail/Outlook, con cualquier disparador | `provider`, `trigger`, `scan_scope`, `initial_scan_complete`, `duration_ms` y conteos agregados |
| `mail_sync_failed` | Una sync falló | `provider`, `trigger`, `error_code`, `duration_ms` |
| `server_error` | Una respuesta 5xx | `route` (plantilla), `method`, `status_code`, `exception_type` |
| `subscription_changed` | Motor de suscripciones | `plan`, `billing_period`, `subscription_event`, `store` |
| `baseline_daily_signups` | Solo con el backfill manual | `count` |

Todos llevan además `success`, `source_type=server`, `environment`, `$process_person_profile=false` y `$geoip_disable=true`.

### Normalización: nombres heredados → canónicos

**El histórico se conserva:**
- Ningún evento de cliente llegó jamás a PostHog (ver §7), así que renombrar los eventos del móvil no pierde datos.
- Los eventos del servidor que sí tienen histórico **no se renombran**.

| Heredado | Canónico | Nota |
|---|---|---|
| `gmail_connection_started` | `mailbox_connection_started` | Ya cubría Gmail y Outlook (`provider`) |
| `mail_connected` (solo Outlook, móvil) | `mailbox_connected` (todos los proveedores, móvil) | Es el paso del funnel |
| `gmail_connected` (servidor) | se mantiene | Señal de salud con histórico. Futuro: `mailbox_connected` en el servidor con `analytics_id` cuando exista identidad (§3), con una Action de PostHog que una ambos nombres |
| `gmail_sync_started/completed/failed` (móvil) | `mail_sync_requested` (móvil) + `mail_sync_completed/failed` (servidor) | La fuente de verdad del resultado es el servidor |
| `gmail_disconnected` | `mailbox_disconnected` | — |
| `email_candidate_reviewed` + `transaction_candidate_reviewed` + `transaction_confirmed` + `transaction_rejected` | `mail_candidate_reviewed` {decision} | Un evento por revisión, sin duplicados |
| `financial_account_ownership_reviewed` + `financial_account_confirmed` | `financial_account_reviewed` {ownership_status} | — |
| `financial_account_detected` | eliminado | Nunca se emitía |
| `salvavidas_saved` / `salvavidas_target_selected` | `useful_action` {action_type=salvavidas_saved} | La allowlist los descartaba en silencio |
| `plan_selected` {change} | `plan_selected` {plan_change} | `change` se descartaba en silencio |
| `screen_viewed` vs `*_opened` | `screen_viewed` en PostHog | `*_opened` es la tabla propia `product_events` (con `account_id`), no PostHog. No se copia a PostHog |

## 5. Propiedades (allowlist)

**Permitidas:** solo las de este contrato, todas cerradas.

- **Categorías:**
  - generales: `plan`, `audience`, `platform`, `environment`;
  - navegación: `screen`, `jarvis_section`, `strategy_tool`;
  - planes: `access_type`, `plan_change`;
  - Email Monitor: `decision`, `review_latency`, `ownership_status`, `provider`, `error_code`;
  - acciones: `action_type`;
  - errores: `endpoint`, `method`, `error_category`.
- **Booleano:** `success`.
- **`app_version`:** solo `x.y.z`.
- **`status_code`:** entero entre 100 y 599.
- **Solo en el servidor:** plantillas de ruta, nombres de clase de excepción, `duration_ms` redondeada y conteos acotados.

**Prohibidas siempre:**
- contenido de correos y PDFs;
- movimientos, montos, saldos, salarios, deudas, patrimonio;
- números de cuenta, IBAN, tarjetas, SINPE, contrapartes, comercios;
- tokens y datos OAuth;
- correo, nombre, teléfono, IP;
- IDs de cuenta, workspace, usuario o buzón;
- URLs y rutas;
- mensajes o stacks de error;
- texto del chat de JARVIS, prompts y eventos de calendario;
- fechas exactas (solo buckets);
- cualquier valor derivado de un correo (fecha del mensaje, clasificación del parser como "transferencia propia", banco). Lo único que sale es la decisión del usuario y un bucket calculado sobre registros propios de DINCR.

**Guards:**
- **Móvil** (`npm run test:product-analytics`):
  - ninguna propiedad permitida tiene nombre sensible;
  - valores hostiles nunca pasan;
  - cada `trackEvent` y `captureProductEvent` del código está en el contrato y no pasa nombres sensibles;
  - el enum `screen` coincide con el registro de páginas y `jarvis_section` con las páginas del Owner;
  - el aislamiento Users/Owner se prueba en ambos sentidos.
- **Servidor** (`backend/product_ops/test_analytics_privacy_contract.py`): los mismos guards de nombres sensibles, valores hostiles y escaneo AST de cada llamada.

## 6. Métricas que el contrato desbloquea

Siempre con el filtro `environment = production`. Las métricas comerciales llevan además `audience = user`.

| Métrica | Definición |
|---|---|
| DAU/WAU/MAU | Usuarios únicos (por dispositivo) de `app_opened` o `app_resumed` |
| Nuevos usuarios | Lifecycle "new" de `app_opened` |
| Sesiones | Sesiones de posthog-js (`$session_id`) en eventos de Users |
| Plataforma / versión / plan | Desglose por `platform`, `app_version` y `plan` |
| Funnel de onboarding | `login_completed` → `onboarding_started` → `onboarding_completed` → `financial_profile_saved` → `useful_action` |
| Primera acción útil | Primer `useful_action` por `action_type` |
| Uso de funciones | `screen_viewed` por `screen` + `strategy_tool_opened` por `strategy_tool` |
| Funnel Email Monitor | `mailbox_connection_started` → `mailbox_connected` → `mail_candidate_reviewed`; salud con `mail_sync_completed/failed` |
| Aceptar/Corregir/Rechazar | `mail_candidate_reviewed` por `decision`, y tiempo por `review_latency` |
| Errores | `api_error`/`app_error` por `app_version` y `platform`; `server_error` por `route` |
| Retención D1/D7/D30 | Retención de `useful_action` → `useful_action`. Abrir la app no cuenta |
| JARVIS | `jarvis_opened` y `jarvis_section_viewed` con `audience = owner` |

**No medibles todavía:**
- **Registro previo a la aceptación legal:** no se envía nada antes del consentimiento.
- **MRR:** no hay fuente de Store billing fiable.
- **Agenda e intents de JARVIS:** requieren instrumentación nativa.

## 7. Configuración (por qué no llegaba nada)

**Apps nativas:** no necesitan ninguna configuración nueva. Usan la API de DINCR que ya tienen, y el backend reenvía con su `POSTHOG_API_KEY`/`POSTHOG_HOST`. Sin esa configuración, el relay no hace nada.

**App Capacitor:**

**Causa:**
- Los builds publicados se compilaron **sin `VITE_POSTHOG_KEY` ni `VITE_POSTHOG_HOST`**.
- Vite inlinea estas variables en tiempo de build. Sin ellas, la condición de `initialize()` se resuelve a `true` y `posthog.init` nunca corre.
- Se verificó en el bundle Android 1.9.11 sincronizado: no contiene ninguna clave `phc_` ni el host `i.posthog.com`.
- No hay pipeline de CI de release ni secretos de PostHog en GitHub Actions: los builds de tienda se hacen a mano (`docs/release/release-pipeline.md`).
- Los usuarios ya instalados **nunca** enviarán eventos: la clave está compilada en el bundle. Se necesita un release nuevo.

| Dónde | Variable | Valor |
|---|---|---|
| Build móvil (máquina que compila Android/iOS) | `VITE_POSTHOG_KEY` | **Project API key** (pública, `phc_…`) del proyecto *DINCR Production*. Nunca una personal/admin key |
| Build móvil | `VITE_POSTHOG_HOST` | `https://us.i.posthog.com`, exactamente así (otro host apaga la analítica) |
| Build móvil | `VITE_ANALYTICS_ENVIRONMENT` | `production` en builds de tienda; `staging` o `development` en builds de prueba |
| Render (backend) | `POSTHOG_API_KEY` / `POSTHOG_HOST` | La misma Project API key y el mismo host (ya configurados: los eventos de servidor llegan) |
| Render | `ANALYTICS_ENVIRONMENT` | Opcional (por defecto `production` en Render) |

Sin clave o con un host fuera de la lista (`us|eu.i.posthog.com`), la analítica queda **apagada**: no se inicializa nada y no se envía nada.

## 8. Si PostHog falla

- **Móvil:** cada llamada va envuelta en `try/catch`; la app nunca espera a PostHog.
- **Servidor:** timeout de 0,5 s para conectar y 1,5 s para leer. Los eventos se encolan en un hilo. Una falla solo deja un warning, sin datos.
- **Pérdidas posibles:** solo los eventos de ese momento.

## 9. Datos históricos

- **Sí:** altas por día mediante `backend/scripts/posthog_signups_baseline.py` (una sola vez, a mano, idempotente).
- **No:** actividad pasada, plan al momento del alta, historial de buzones ni resultados de syncs. Todo eso empieza a medirse desde el release.

## 10. Privacidad y gates humanos

- **Antes de distribuir un build con `VITE_POSTHOG_KEY`:**
  1. PostHog → **Discard client IP data** activado. Está activado: `anonymize_ips=true` en el proyecto.
  2. La Política de Privacidad vigente nombra a PostHog como analítica de producto anónima. El contrato v2 sigue siendo anónimo por dispositivo.
  3. Grabación de sesiones y captura de logs de consola **desactivadas a nivel de proyecto**. El SDK también las desactiva.
- **Pseudónimo estable:** exige una versión legal nueva (§3).
- **Firebase:** solo distribuye builds de prueba; no observa usuarios.

## 11. Verificación física mínima (teléfono → PostHog)

1. **Capacitor:** compilar con `VITE_POSTHOG_KEY` y `VITE_POSTHOG_HOST` e instalar en Android e iOS. **Nativo:** un build `release` contra el backend de producción (`debug` se etiqueta `development`).
2. **Cuenta User** con los documentos aceptados. En Live events deben aparecer:
   - `app_opened` y `login_completed`;
   - `screen_viewed` al navegar;
   - `strategy_tool_opened`;
   - `useful_action` al crear una meta;
   - `app_resumed`;
   - `logout`.
   Todos con `audience=user`.
3. **Cuenta Owner** (requiere su aceptación legal registrada, ver §2):
   - solo `jarvis_opened` y `jarvis_section_viewed`, con `audience=owner`;
   - al usar Estrategia o el Chat, **ningún** evento de Users ni texto.
4. **Abrir un evento.** Debe tener:
   - solo las propiedades de su tabla y las comunes;
   - `token`, `distinct_id`, `$process_person_profile=false` y `$geoip_disable=true`.
   No debe tener URL, correo, banco, montos, IDs, `$set` ni fechas.
5. **Persons:** no debe haber perfiles nuevos.
6. **Correo:**
   - conectar Gmail: `mailbox_connection_started`, luego `mailbox_connected` (móvil), `gmail_connected` y `mail_sync_completed` (`trigger=connect`), ambos del servidor;
   - revisar un candidato: un único `mail_candidate_reviewed`.
7. **Red:**
   - **Capacitor:** solo `/e/` y `/array/<key>/config`.
   - **Nativo:** solo `POST /product-ops/analytics` a la API de DINCR; ninguna llamada a PostHog desde el teléfono.
8. **Nativo, en PostHog:** los eventos llevan `client=native` y el `distinct_id` es el UUID de instalación. Tras cerrar sesión, el UUID cambia.
