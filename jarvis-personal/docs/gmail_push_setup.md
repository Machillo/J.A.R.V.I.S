# Gmail Push automático — configuración

El código queda inactivo hasta configurar Google Cloud y Render. El escaneo
manual existente continúa funcionando aunque estas variables estén vacías.

## Variables en Render

- `GMAIL_PUBSUB_TOPIC`: `projects/PROJECT_ID/topics/jarvis-gmail`
- `GMAIL_PUBSUB_VERIFICATION_TOKEN`: valor aleatorio largo y privado
- `EMAIL_MONITOR_CRON_SECRET`: valor aleatorio largo y privado

No guardar estos valores en Git.

## Google Cloud

1. Habilitar Gmail API, Cloud Pub/Sub y Cloud Scheduler.
2. Crear el topic `jarvis-gmail`.
3. Dar a `gmail-api-push@system.gserviceaccount.com` permiso
   `roles/pubsub.publisher` sobre el topic.
4. Crear una suscripción push hacia:
   `https://RENDER_HOST/email-monitor/gmail-push?token=VERIFICATION_TOKEN`.
5. Crear un Scheduler diario que haga `POST` a
   `https://RENDER_HOST/email-monitor/gmail-watch` con el header
   `X-Jarvis-Cron-Secret: CRON_SECRET`.
6. Ejecutar una vez el mismo `POST /email-monitor/gmail-watch` para activar el
   primer watch. Gmail exige renovarlo al menos cada siete días.

## Base de datos

Aplicar `database/migrations/20260901_gmail_push_automation.sql` en Supabase
antes de activar el primer watch. El backend también agrega esas columnas de
forma idempotente al usar el monitor.

## Comportamiento

- Pub/Sub solo despierta JARVIS; no incluye el contenido del correo.
- JARVIS consulta `history.list` y descarga únicamente mensajes nuevos de INBOX.
- Cada correo pasa por el parser y deduplicador existentes.
- Los movimientos quedan pendientes; el auto-guardado sigue desactivado.
- Si el historial expiró, JARVIS recupera con el escaneo acotado al ciclo BAC.
