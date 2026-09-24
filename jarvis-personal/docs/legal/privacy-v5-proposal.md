# Propuesta: Política de Privacidad v5 (LEGAL / PRE-RELEASE GATE)

**Estado: NO publicada.** Esta propuesta prepara el cambio mínimo para que la política describa el comportamiento real después de retirar Firebase Analytics y Crashlytics de la app. No modifica el texto vigente ni fuerza una nueva aceptación. Requiere aprobación humana, incluida una revisión legal.

## Por qué

- Desde que se retiró Firebase del runtime, la app no contiene SDK de Firebase, ni Analytics, ni Crashlytics, y Firebase no recibe datos de usuarios. Firebase se usa solo como servicio externo de **Firebase App Distribution**, para distribuir APK de prueba a testers invitados.
- PostHog es el único sistema de analítica, con el contrato de privacidad de `docs/analytics/posthog-event-taxonomy.md`.
- La v4 vigente (`2026-09-25-v4`) todavía dice en §5: "Google (Gmail y, en Android, Firebase Analytics y Crashlytics para métricas de uso y diagnóstico de errores)". Declara un tratamiento que ya no existe.

## Cambio exacto propuesto (`frontend/src/pages/PublicInfoPage.jsx`, `PrivacyPage`)

**§5 Proveedores y transferencias.** Reemplazar:

> Google (Gmail y, en Android, Firebase Analytics y Crashlytics para métricas de uso y diagnóstico de errores)

por:

> Google (Gmail y, solo para personas invitadas a probar versiones previas, Firebase App Distribution para distribuir esas versiones de prueba; la aplicación no incluye Firebase ni le envía datos de uso)

El resto de §5, incluida la descripción de PostHog, queda igual.

**§2 Datos tratados** ("eventos de uso, diagnósticos de errores y datos básicos del dispositivo") y **§3 Finalidades** ("diagnosticar fallos") siguen siendo correctos: hoy los cubre PostHog (anónimo). No cambian.

**Encabezado.** `VERSIÓN 2026-XX-XX-v5 · VIGENTE DESDE …`, con la fecha real de publicación.

## Mecanismo que se activaría

1. `backend/auth/legal.py`: `PRIVACY_VERSION = "<fecha>-v5"`.
2. `legal_status()` devolverá `required: true` para **todas** las cuentas, porque no existe aceptación con la versión nueva. En el siguiente inicio de sesión, la app muestra `LegalConsent` y pide aceptar de nuevo Términos v3 y Privacidad v5. La evidencia queda en `legal_acceptances` (versiones, IP y user-agent, `ON CONFLICT DO NOTHING`).
3. Hay que actualizar a la vez la versión mostrada en `frontend/landing/build.mjs` (`/privacidad/`) y el contrato `frontend/scripts/test-dincr-public-contract.mjs`. Ese test ya exige que, con una versión posterior a v4, `/privacidad/` no mencione Firebase Analytics ni Crashlytics.
4. Decisión humana: si reducir un proveedor justifica pedir una nueva aceptación, o si alcanza con una nota de cambios. Hoy el sistema solo soporta "versión nueva = reaceptación".

## Relacionado (no incluido, decidir por separado)

- **Términos v3 §2** dice: "contenido generado con automatización o inteligencia artificial". DINCR no usa IA generativa en runtime. Corregirlo exige una versión nueva de Términos (`TERMS_VERSION`) y también reaceptación. Conviene agruparlo con la v5 para pedir **una sola** reaceptación.
- **Google Play → Data safety:** dejar de declarar datos de Firebase Analytics y Crashlytics en el próximo build.
