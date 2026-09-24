# Buzones de correo DINCR

El acceso al correo es por buzón y requiere consentimiento del usuario y plan VIP.
DINCR solo solicita lectura. Gmail sigue con Gmail API; Outlook y Hotmail usan
Microsoft Graph con permisos delegados `Mail.Read`, `User.Read` y `offline_access`.
No se solicita ni se almacena la contraseña del correo. Los refresh tokens se
guardan en Supabase Vault en el backend y se eliminan al desconectar.

## Cómo se vincula un buzón (Gmail y Outlook)

1. La app autenticada llama a `connect`. El backend crea un flujo en
   `mail_oauth_flows` (solo el hash del `state`, proveedor, cuenta, workspace,
   verificador PKCE, 10 minutos) y devuelve la URL de autorización con PKCE (S256).
2. Google/Microsoft redirigen el navegador del sistema al callback público. El
   callback acepta el `state` una sola vez y solo para su proveedor, canjea el
   código con el verificador PKCE, guarda el refresh token en Vault como
   *pendiente* y vuelve a la app con un código de un solo uso.
3. La app, con la sesión que inició el flujo, canjea ese código en
   `POST /user-product/vip/mail/oauth/complete`. Solo entonces se vincula el buzón.
   Si otra cuenta o workspace intenta canjearlo, el token pendiente se elimina.

Así, quien comparta su enlace de autorización no puede vincular el correo de otra
persona a su cuenta (account-linking CSRF). Los flujos abandonados liberan su
token pendiente en el mantenimiento programado. Requiere la migración
`20260924120000_mail_oauth_flows.sql` antes de desplegar el backend.

## Habilitar Outlook/Hotmail

1. Registrar una aplicación en Microsoft Entra para **cuentas de cualquier
   directorio y cuentas personales Microsoft**. La autorización usa el
   endpoint `common`, que acepta Outlook.com/Hotmail/Live y Microsoft 365.
2. En *Authentication → Web*, agregar el URI de redirección del backend:
   `https://api.dincr.com/user-product/vip/mail/microsoft/callback`.
3. Permitir permisos delegados Microsoft Graph `Mail.Read` y `User.Read`.
   `offline_access` se solicita en la autorización para obtener el refresh
   token de las sincronizaciones posteriores. Crear un client secret para el
   backend. **No** ponerlo en el frontend, la APK ni Git.
4. Configurar solamente en el backend:
   - `MICROSOFT_CLIENT_ID`
   - `MICROSOFT_CLIENT_SECRET`
   - `MICROSOFT_REDIRECT_URI` (idéntico al registrado)

   Los nombres anteriores `FINVA_MICROSOFT_*` siguen aceptándose.
5. Desplegar el backend. La opción de Outlook permanece desactivada hasta que
   las tres variables estén configuradas. Outlook no tiene notificaciones push:
   se actualiza con "Actualizar todos" y con el cron de mantenimiento de Gmail.
6. Probar autorización, primer escaneo, otro Gmail conectado, revisión de un
   aviso bancario, sincronización de mantenimiento y desconexión en dispositivo.

Antes de abrir Google o Microsoft, la persona elige el historial a revisar:
`current_month` (desde el día 1 del mes actual) o `current_year` (desde el 1 de
enero). La elección se guarda en el flujo OAuth del servidor y pasa a la conexión
(`import_since`); reconectar solo reinicia el escaneo si amplía el período.
Sin elección (versiones anteriores de la app) se usa `current_year`.

El primer escaneo procesa páginas de hasta 50 avisos desde `import_since`;
las siguientes ejecuciones continúan desde el cursor. Los escaneos posteriores
revisan avisos recientes. Solo se procesan remitentes financieros admitidos
por el parser y no se almacenan otros mensajes de la bandeja. Los PDFs
financieros se procesan con el mismo flujo de revisión que Gmail.

## Yahoo

Yahoo no proporciona acceso de correo IMAP/OAuth mediante autoservicio para
aplicaciones externas. DINCR **no** ofrece hoy un conector Yahoo. El operador
de DINCR debe solicitar y obtener aprobación para el scope de lectura de Yahoo
antes de activar un conector IMAP con OAuth. No pedir contraseñas ni contraseñas
de aplicación Yahoo como sustituto. No anunciar Yahoo como compatible hasta
probar el flujo autorizado con una cuenta real.

Referencias oficiales: [Microsoft Graph Mail.Read](https://learn.microsoft.com/en-us/graph/permissions-reference#mailread),
[flujo delegado de Microsoft](https://learn.microsoft.com/en-us/graph/auth-v2-user),
[acceso para desarrolladores de Yahoo](https://senders.yahooinc.com/developer/developer-access/).
