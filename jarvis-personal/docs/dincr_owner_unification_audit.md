# DINCR: lanzamiento, marca y Owner — auditoría de código (2026-09-23)

## Base revisada

`main` en `13875f5`; PR #176 estrategia determinista, #177 estrategia VIP, #178 preparación stores/eliminación, #179 landing y #180 Cloudflare, todos fusionados antes de esta rama. El repo contiene la app móvil DINCR, una experiencia interna heredada en `frontend/src/personal/PersonalApp.jsx` y una landing estática independiente. Vercel conserva `frontend/vercel.json` y el build de la app; Cloudflare debe publicar únicamente `landing-dist/`.

## Capacidades internas preservadas

`PersonalApp` sigue montando asistente/chat, estrategia, finanzas, patrimonio, inversiones/IBKR, negocios, cuentas, conciliación, deterioro, correos, transacciones, memoria, notificaciones, calendario, deportes, configuración, usuarios y operaciones. La UI se presenta como DINCR Owner; los nombres de código `jarvis`, clases CSS, rutas `/jarvis/*`, variables del puente, carpetas y `com.jarvis.personal` quedan por compatibilidad. Ninguna tabla, workspace ni dato se renombró o movió. El proyecto iOS Owner separado (`com.jarvis.personal`) se eliminó: DINCR Owner vive dentro de la única app iOS, DINCR (`com.dincr.app`).

## Límite de seguridad

El token Supabase se comprueba contra `/auth/v1/user` en el backend; `allowed_users.role` y `accounts.role` se sincronizan allí. `OWNER_EMAILS` es configuración **servidor**, no email hardcodeado en cliente. El puente interno exige clave de servidor, firma HMAC, expiración, identidad `allowed_users` activa con rol owner y contexto del workspace propio. El hash/localStorage del cliente solo puede presentar un token; cambiarlo no crea una firma válida. Se bloquea la creación de `role=owner` por `/auth/allowed-users`. El router interno `/jarvis/*` exige rol Owner/Admin incluso para peticiones directas; `/users-admin/*` y `/product-ops/owner/*` exigen Owner. `owner` no existe entre los planes de `/auth/plan` y no se vende por billing. Admin es otro rol heredado con acceso al entorno interno, sin capacidad para aprovisionar Owner por API; revisar su alcance antes de distribución si existiesen cuentas admin.

Las pruebas cubren Free/Basic/VIP con `isOwner=true`, plan `owner` inválido, creación Owner por API, dependencia del router, token alterado, cambio de rol en DB, rechazo de emisión para rol normal y acceso Owner válido. Son pruebas locales con dobles de DB; **no** prueban políticas RLS, Supabase, Render ni sesiones reales en dispositivos. La comprobación de identidad por email del backend y los UID del puente requieren una prueba de integración con las cuentas reales antes del lanzamiento.

## Precio y datos

Free ₡0, Basic ₡2.990/mes, VIP ₡4.990/mes en `product_ops/service.py`, catálogo store, ajustes de frontend, landing y términos. La migración nueva corrige el default y filas antiguas de `finva_beta_programs` con 5990, dejando intactos pedidos, pagos y suscripciones históricos. Debe aplicarse en la base de datos antes de ofrecer el precio nuevo; no se aplicó aquí. El valor 5990 de la migración histórica de 20260910 y el `WHERE` de la migración correctiva permanecen como evidencia histórica. `FINVA_VIP_ANNUAL_CRC` puede sobreescribir el precio anual en el entorno; el precio anual no fue aprobado y los product IDs existentes son valores provisionales, no productos de store configurados.

## Legal y contacto

Términos y privacidad muestran solo DINCR y `soporte@dincr.com`, con versión `2026-09-23-v2` sincronizada con `backend/auth/legal.py`; las cuentas existentes volverán a aceptar los textos. La landing reutiliza las secciones legales. La dirección de correo aún no tiene servicio/MX verificado: no publicar como canal utilizable antes de configurarlo. Es necesaria revisión jurídica del texto nuevo antes de lanzar.

## Superficies y límites

Login, onboarding, consentimiento, títulos, owner UI, mensajes visibles, títulos de notificación y nombre iOS heredado muestran DINCR. El manifest y configuración Android/Finva iOS ya muestran DINCR. El código retiene nombres internos históricos `JARVIS`, `FINVA`, identificadores de plugins, rutas, modelos, tablas y migraciones para evitar romper contratos. Las transacciones históricas pueden conservar notas antiguas; no se reescribieron. Los prompts internos se limitaron al cambio de identidad, sin alterar cálculo determinista ni arquitectura AI. No se verificó visualmente cada pantalla en dispositivo ni la salida generativa real de IA.

La landing generó nueve rutas, canonical/sitemap en `https://dincr.com`, VIP ₡4.990 y contacto público; la salida no carga bundle, autenticación ni PostHog. `npm ci`, frontend build, landing build, lint, tests de navegación, analytics, store, locale y landing, y 198 tests backend pasaron; lint conserva 14 warnings previos. Cloudflare, DNS, correo, OAuth, tiendas, RLS en vivo, pruebas de integración de billing, migración aplicada y stores/dispositivos siguen pendientes.
