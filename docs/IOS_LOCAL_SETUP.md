# DINCR en iPhone

El repositorio contiene **una sola** aplicación iOS, DINCR. DINCR Owner no es una
app aparte: aparece dentro de DINCR según el rol de la cuenta.

| Aplicación | Bundle ID | Proyecto Xcode | Target / scheme |
| --- | --- | --- | --- |
| DINCR | `com.dincr.app` | `jarvis-personal/frontend/ios-dincr/App/App.xcodeproj` | `App` |

La configuración de Capacitor para iOS es `frontend/capacitor.ios.dincr.json`. La
configuración por defecto (`frontend/capacitor.config.json`) sigue siendo la de
Android y no cambia al trabajar con iOS.

## Preparar la Mac

Desde `jarvis-personal/frontend`:

```bash
npm ci
npm run ios:open
```

`ios:open` crea el build web con `VITE_NATIVE_APP_ID=com.dincr.app`, sincroniza
Capacitor, verifica que el proyecto generado sea `com.dincr.app` con el
onboarding biométrico y abre Xcode. Para sincronizar sin abrir Xcode: `npm run ios:sync`.

## Firma

1. En Xcode, abrir el target `App` → **Signing & Capabilities**.
2. Activar **Automatically manage signing** y elegir el equipo de Apple Developer.
   El equipo no se guarda en Git; certificados y perfiles tampoco.
3. Conectar y desbloquear el iPhone, seleccionarlo como destino y ejecutar con **Run**.

## Deep links

`Info.plist` registra:

- `com.dincr.app` — scheme principal. Inicio de sesión nativo:
  `com.dincr.app://auth/callback` (debe estar permitido en Supabase Auth → URL Configuration).
- `com.finva.app` — **transitorio**, solo para `/gmail/callback`. El backend devuelve el OAuth
  de Gmail/Outlook a un único scheme para todas las plataformas (`FINVA_GMAIL_RETURN_URL`,
  hoy `com.finva.app://gmail/callback`). Android e iOS ya son `com.dincr.app` y registran
  ese callback transitorio. Quitarlo en ambas plataformas cuando esa variable apunte a
  `com.dincr.app://gmail/callback`.

Desinstalar cualquier build iOS anterior (`com.finva.app` o `com.jarvis.personal`)
antes de probar: dos apps con el mismo scheme hacen impredecible el regreso del OAuth.

## Firebase

El build iOS no incluye Firebase Analytics ni Crashlytics. Para agregarlos hay que
registrar `com.dincr.app` en Firebase y añadir su `GoogleService-Info.plist`.
