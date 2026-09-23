# Buzones de correo DINCR

El acceso al correo es por buzón y requiere consentimiento del usuario y plan VIP.
DINCR solo solicita lectura. Gmail sigue con Gmail API; Outlook y Hotmail usan
Microsoft Graph con permisos delegados `Mail.Read`, `User.Read` y `offline_access`.
No se solicita ni se almacena la contraseña del correo. Los refresh tokens se
guardan en Supabase Vault en el backend y se eliminan al desconectar.

## Habilitar Outlook/Hotmail

1. Registrar una aplicación en Microsoft Entra para **cuentas personales Microsoft**.
   La autorización usa el tenant `consumers` y un redirect web HTTPS del backend.
2. Agregar el URI de redirección del backend:
   `https://<backend-oficial>/user-product/vip/mail/microsoft/callback`.
3. Permitir permisos delegados Microsoft Graph `Mail.Read` y `User.Read`.
   `offline_access` se solicita para sincronizaciones posteriores. Crear un
   client secret para el backend. **No** ponerlo en el frontend, la APK ni Git.
4. Configurar solamente en el backend:
   - `DINCR_MICROSOFT_CLIENT_ID`
   - `DINCR_MICROSOFT_CLIENT_SECRET`
   - `DINCR_MICROSOFT_REDIRECT_URI` (idéntico al registrado)
5. Desplegar backend y APK actualizados. La opción de Outlook permanece
   desactivada hasta que las tres variables estén configuradas.
6. Probar autorización, primer escaneo, otro Gmail conectado, revisión de un
   aviso bancario, sincronización de mantenimiento y desconexión en dispositivo.

El primer escaneo procesa páginas de hasta 50 avisos desde el inicio del año;
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
