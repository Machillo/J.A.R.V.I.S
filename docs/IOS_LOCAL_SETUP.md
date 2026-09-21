# FINVA y J.A.R.V.I.S. en iPhone

El repositorio contiene dos aplicaciones iOS independientes que comparten el frontend y la API:

| Aplicación | Bundle ID | Proyecto Xcode |
| --- | --- | --- |
| FINVA | `com.finva.app` | `frontend/ios-finva/App/App.xcodeproj` |
| J.A.R.V.I.S. | `com.jarvis.personal` | `frontend/ios-jarvis/App/App.xcodeproj` |

Ambas pueden permanecer instaladas al mismo tiempo. La configuración Android existente continúa usando `frontend/capacitor.config.json` y no cambia.

## Preparar la Mac

Desde `jarvis-personal/frontend`:

```bash
npm install
```

Crear el build, sincronizar Capacitor y abrir Xcode:

```bash
npm run ios:open:finva
npm run ios:open:jarvis
```

Los comandos preservan automáticamente la configuración canónica de Android. Para sincronizar sin abrir Xcode se pueden usar `ios:sync:finva` e `ios:sync:jarvis`.

## Firma gratuita para un iPhone personal

En cada proyecto de Xcode:

1. Abrir el target `App` y entrar a **Signing & Capabilities**.
2. Activar **Automatically manage signing**.
3. Elegir el Apple ID personal en **Team**.
4. Conectar y desbloquear el iPhone, seleccionarlo como destino y ejecutar con **Run**.

## Inicio de sesión nativo

Los callbacks usados son:

- `com.finva.app://auth/callback`
- `com.jarvis.personal://auth/callback`

Ambos deben estar permitidos en la configuración de redirecciones de Supabase Auth. Los esquemas ya están registrados en cada `Info.plist`.

## Firebase para una etapa posterior

Analytics y Crashlytics quedan fuera del build iOS inicial hasta registrar las dos aplicaciones iOS en Firebase y agregar su `GoogleService-Info.plist` correspondiente. Esto evita inicializar Firebase con una configuración inexistente durante las pruebas personales. Android conserva su integración actual.
