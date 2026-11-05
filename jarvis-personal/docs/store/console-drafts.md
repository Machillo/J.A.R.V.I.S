# Borradores para las consolas de Google y Apple

Son borradores para que los revise el responsable antes de enviarlos. Describen el código de `main` al escribirlos. Si cambia lo que la app recoge, hay que actualizarlos junto con la Política de Privacidad.

## Decisiones ya tomadas

- Publica una persona, no una empresa.
- Solo iPhone y Android. Sin iPad, tabletas ni Mac.
- Gratis hasta el 31 de marzo de 2027, sin compras dentro de la app durante esa promoción.
- La lectura de correo es solo del rol interno al lanzar: no se anuncia.

## Notas para quien revisa (App Store y Google Play)

```text
DINCR is a personal finance organizer for Costa Rica. Users record income, expenses,
debts and goals, and see calculations based on their own data. DINCR does not move money,
hold funds, offer loans, or execute investments, and it is not a bank or a financial adviser.

Sign in: use the test account provided in the access section.

Plans: Basic and VIP are free until March 31, 2027. There are no purchases in this
version. After that date, purchases will use the App Store or Google Play.

Internal role: the app contains an internal role available only to the developer's own
account, decided by the server. It is not offered, sold or reachable by users or by this
test account. It includes the developer's own bank mail reading, which is why the build
references read-only mail access. Regular accounts cannot connect a mailbox.

Account deletion: Profile, then Delete my account (on Android, Profile, Account settings,
Delete my account).
```

La cuenta de prueba la crea el responsable, con datos inventados. Nunca debe ser una cuenta real ni tener el rol interno.

## Google Play: Seguridad de los datos

| Dato | ¿Se recoge? | Para qué | Notas |
|---|---|---|---|
| Nombre y correo | Sí | Cuenta | Vienen de Google o Apple al iniciar sesión |
| Información financiera del usuario | Sí | Funciones de la app | Ingresos, gastos, deudas, metas y saldos que el usuario ingresa |
| Actividad en la app (interacciones) | Sí | Analítica | La app le avisa a nuestro servidor de eventos de uso, como abrir una función, sin montos ni descripciones. Quedan ligados a la cuenta y se borran con ella. El servidor además envía a PostHog contadores anónimos, que no identifican a la persona |

- Datos cifrados en tránsito: sí (HTTPS).
- El usuario puede pedir que se borren: sí, desde la app y en `dincr.com/eliminar-cuenta/`.
- Se venden o se comparten con terceros para publicidad: no.
- Anuncios: no.

Datos que **no** se recogen en una cuenta normal: ubicación, contactos, fotos, SMS como permiso del sistema (lo que el usuario comparte es texto que él elige enviar), correo electrónico del buzón.

Permisos de Android: internet, estado de la red, biometría (también aparece el permiso antiguo de huella), notificaciones, arrancar con el teléfono (para volver a poner recordatorios) y compras de Google Play (`BILLING`, viene con la librería de compras; no se cobra nada mientras no haya productos creados).

## Google Play: Funciones financieras

Elegir finanzas personales: gestión de presupuesto y seguimiento de gastos. No marcar préstamos, inversiones, pagos, banca ni criptomonedas.

## App Store: Privacidad de la app

- Información de contacto: nombre y correo, vinculados a la persona, para funcionalidad de la app.
- Información financiera: "otra información financiera", vinculada a la persona, para funcionalidad de la app.
- Uso: "interacción con el producto", vinculada a la persona, para analítica.
- Seguimiento entre apps: no.

Tiene que coincidir con `native/ios/DINCR/Resources/PrivacyInfo.xcprivacy`.

## Consolas: ajustes de dispositivos

- App Store Connect: desmarcar la disponibilidad en Mac con Apple Silicon.
- Google Play: excluir tabletas en el catálogo de dispositivos.

## Pendiente de confirmar antes de enviar

- Copias de respaldo: el plan gratis de Supabase no incluye copias automáticas. Antes de enviar, decidir si se sube de plan (el plan Pro guarda 7 días) y mantener las copias manuales dentro de los 30 días que promete la política.
- Texto de la ficha de cada tienda: borrador en `listing.md`.
