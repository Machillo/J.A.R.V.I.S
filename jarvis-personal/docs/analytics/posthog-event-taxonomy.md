# DINCR: PostHog en producción

## Auditoría de `main` antes del cambio

- Existían `posthog-js`, `src/lib/productAnalytics.js`, eventos puntuales y la
  infraestructura Firebase Analytics/Crashlytics. La clave `VITE_POSTHOG_KEY`
  estaba vacía en `.env.example`; ningún evento podía confirmarse en producción.
- La versión anterior permitía todas las propiedades que empezaran con `$` y
  valores libres como nombres de bancos. Ahora se eliminan esas propiedades.
- Render guarda `product_events` en PostgreSQL: no son eventos PostHog y no se
  reenvían automáticamente. No había SDK Python ni clave PostHog en Render.

## Contrato de privacidad

- Solo la compilación **nativa DINCR** (Android/iOS), después de aceptar las
  versiones legales vigentes, envía eventos explícitos. Se excluyen JARVIS,
  propietario/admin, Vercel y la landing pública.
- PostHog usa un identificador **anónimo del dispositivo** que cambia al salir
  de la sesión. No se llama `identify`, no se crean perfiles de persona y no se
  envían ID de cuenta/workspace, correo ni etiquetas libres.
- Desactivados: autocapture, pageviews automáticas, Replay, excepciones,
  encuestas, flags, parámetros de campañas, referente y geolocalización por IP.
  `before_send` reconstruye el evento con una lista cerrada de propiedades más
  tres técnicas: `token` (la Project API key pública, **obligatoria**: sin ella
  posthog-js descarta el evento antes de enviarlo), `$process_person_profile:
  false` y `$geoip_disable: true`.
- PostHog recibe la IP de la conexión aunque no la guarde como propiedad: la
  opción `ip: false` de posthog-js no tiene efecto. `$geoip_disable` evita la
  geolocalización; para no conservar la IP hay que activar **Discard client IP
  data** en la configuración del proyecto PostHog (acción manual en el panel).
- El servidor solo emite eventos agregados `gmail_connected` y
  `account_deletion_completed`, usando un ID aleatorio **nuevo por evento**;
  no envía IDs, IP del usuario, Gmail ni datos financieros. Se envían después
  de una operación exitosa y en `BackgroundTasks`. Se mantiene el registro
  operativo existente en PostgreSQL, que no se reenvía a PostHog.
- Si falta configuración o PostHog falla, la app y la API continúan operando.

## Eventos del móvil

`app_opened`, `app_resumed`, `screen_viewed`, `onboarding_started`,
`onboarding_completed`, `plan_selected`, `plan_access_granted`,
`gmail_connection_started`, `mail_connected` (Outlook), `gmail_sync_started`,
`gmail_sync_completed`, `gmail_sync_failed`, `gmail_disconnected`,
`financial_account_confirmed`, `financial_account_ownership_reviewed`,
`email_candidate_reviewed`, `transaction_candidate_reviewed`, `transaction_confirmed`,
`transaction_rejected`, `account_deletion_started`,
`account_deletion_failed`, `data_export_completed`.

`financial_account_detected` está reservado en la lista, pero no se emite
todavía: no hay un punto de creación único confirmado para todos los proveedores.
`gmail_connected` se confirma en el callback OAuth del backend; una conexión
Outlook/Hotmail se registra como `mail_connected` desde la app.

## Propiedades permitidas

`plan` (free/basic/vip), `platform` (android/ios), `screen` (lista cerrada de
destinos), `access_type` (free/promotion), `source_type` (email/manual),
`decision` (accepted/corrected/rejected), `ownership_status` (own/not_mine),
`scan_scope` (recent/year_to_date/current_month), `success`, `initial_scan_complete`,
`app_version` (versión numérica) y `duration_ms` (redondeada al segundo y
limitada a 60 s). El contrato está en `frontend/src/lib/analyticsContract.js`.
Ninguna cifra económica, nombre de banco, correo, ruta/URL, descripción, saldo,
deuda, token, documento ni valor escrito por un usuario está permitido.

## Variables manuales

| Destino | Variable | Valor |
| --- | --- | --- |
| Compilación móvil `jarvis-personal/frontend` (Mac/CI) | `VITE_POSTHOG_KEY` | **Project API key** del proyecto DINCR, nunca personal/admin API key |
| Compilación móvil `jarvis-personal/frontend` (Mac/CI) | `VITE_POSTHOG_HOST` | `https://us.i.posthog.com` o `https://eu.i.posthog.com`, según la región real |
| Backend Render (opcional para dos eventos agregados) | `POSTHOG_API_KEY` | La **misma Project API key**, no una clave administrativa |
| Backend Render (opcional para dos eventos agregados) | `POSTHOG_HOST` | El **mismo host** que el build móvil |

Render **no** inyecta variables `VITE_*` en una APK ya compilada. Recompilar
`npm run build` y sincronizar Capacitor para ambos sistemas operativos. La
landing Cloudflare Pages no necesita ni debe recibir estas variables.
Sin las claves, la integración permanece desactivada de forma segura.

## Revisión legal antes de encender las claves

La Política de Privacidad v2 menciona eventos de uso, diagnósticos, proveedores
de monitoreo y transferencias internacionales, pero **no nombra PostHog**, su
región ni la retención de identificadores anónimos. Antes de activar PostHog
en producción, revisar jurídicamente si hay que mencionar proveedor, país,
propósitos de analítica, período de conservación, revocación y eliminación; si
es un cambio material, publicar versión nueva y renovar la aceptación. No se
modificó el texto legal en esta implementación.

## Verificación tras configurar y desplegar

1. En PostHog, verificar organización/proyecto DINCR, host regional y obtener
   **Project API key** en Project Settings. No copiar una personal API key.
2. Definir variables en el entorno de build de la APK/IPA y, si se activan los
   eventos agregados del backend, en Render. Desplegar la nueva versión.
3. Abrir la APK nueva en Android/iOS con una cuenta normal que aceptó la política.
   En PostHog → Activity / Live events buscar `app_opened`, `screen_viewed`,
   `plan_selected` o `gmail_sync_started`.
4. Inspeccionar un evento: confirmar que solo lleva las propiedades permitidas;
   revisar que NO contiene URL, correo, banco, cuentas ni montos. Confirmar
   ausencia de Replay y de eventos de JARVIS o la landing.
5. Para probar Render, completar una conexión Gmail real y buscar
   `gmail_connected` como evento agregado. La eliminación de una cuenta real
   es irreversible: no usarla como prueba de humo.

No hay retroactividad: los usuarios con APK anterior o sin `VITE_POSTHOG_KEY`
seguirán sin emitir nuevos eventos hasta instalar una versión recompilada.

## Corrección de envío (auditoría pre-release)

Hasta esta corrección **ningún evento móvil llegaba a PostHog**. `before_send`
eliminaba la propiedad `token` y posthog-js 1.434 descarta en el cliente
cualquier evento sin ella; el test usaba un stub que no reproducía esa regla.
Ahora `test:product-analytics` también ejecuta el pipeline real de posthog-js.
Los dos eventos del servidor sí se enviaban, pero creaban un perfil de persona
por evento; ahora envían `$process_person_profile: false`.

## Antes de distribuir un build con `VITE_POSTHOG_KEY` (HUMAN GATE)

Ahora que los eventos sí llegan, esto va **antes** de enviar cualquier build con
la clave a usuarios reales (no después de la prueba):
1. PostHog → Project settings → activar **Discard client IP data**.
2. Revisión legal: la Política de Privacidad debe nombrar PostHog (proveedor,
   región, propósito, retención del ID anónimo) — ver sección anterior.
3. Firebase Analytics/Crashlytics (fuera de este contrato): reciben el ID
   interno de cuenta (`setUserId`), pantallas Owner y texto de errores, sin
   gating por rol ni aceptación legal (`src/lib/telemetry.js`). Requiere
   decisión de producto/legal antes del release.

## Prueba física mínima (teléfono → PostHog)

1. Compilar con `VITE_POSTHOG_KEY` y `VITE_POSTHOG_HOST` definidos; `npm run
   android:apk` avisa si falta la clave. Instalar en Android (y la IPA en iOS).
2. Iniciar sesión con una cuenta **User** Free/Basic/VIP que ya aceptó los
   documentos legales vigentes.
3. PostHog → Activity/Live events, en menos de 1 minuto:
   `app_opened` → navegar a Movimientos (`screen_viewed`, `screen=transactions`)
   → enviar la app a segundo plano y volver (`app_resumed`).
4. Abrir un evento: solo `plan`, `platform`, `app_version`, `screen`, `token`,
   `distinct_id`, `$process_person_profile=false`, `$geoip_disable=true`. Sin
   `$current_url`, correo, banco, montos, IDs de cuenta ni propiedades `$set`.
5. Persons: no debe aparecer ningún perfil nuevo.
6. Cerrar sesión → iniciar con **otra** cuenta: `app_opened` con otro
   `distinct_id`.
7. Iniciar sesión como **Owner** y como cuenta sin aceptación legal: no debe
   llegar ningún evento.
8. Conectar Gmail: debe llegar **un solo** `gmail_connected` (servidor) y ningún
   `mail_connected`; conectar Outlook: un `mail_connected`.
9. Red: solo `/e/` y `/array/<key>/config`; nada de `/flags` ni scripts externos.
