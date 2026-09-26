# DINCR native apps (prototype)

Native DINCR for iOS (Swift + SwiftUI) and Android (Kotlin + Jetpack Compose). This is the
**representative prototype** (phase C4): login, profile setup, Home (Free overview), Movements,
add/edit/delete movement, profile/appearance/sign-out. Everything else shows an honest
"under construction" screen with its parity IDs. The Capacitor app in `frontend/` stays the
production app until the parity matrix (`docs/native/PARITY_MATRIX.md`) is complete.

## Rules

- **Business logic stays in FastAPI.** Native code presents, navigates and integrates with the
  platform. It never computes financial results; every figure on screen is a backend value.
  Client-side calculations found in Capacitor are listed in
  `docs/native/CURRENT_STATE_AUDIT.md` §5 as backend dependencies.
- **Same API contract as the web client**: bearer token, `Accept-Language`, stable
  `X-Request-ID`, retries only for safe methods, one token refresh on 401, 20 s timeout.
- **Owner boundary**: an Owner/admin session sees a notice, never Owner features.
- **Design tokens come from `/DESIGN.md`.** Never edit the generated files.
- **No real data in fixtures.** Fixture mode uses invented names and amounts.

## Layout

```
native/
  design-tokens/generate.mjs   DESIGN.md → Swift + Kotlin tokens (--check for drift)
  ios/
    DINCR.xcodeproj            app + UI tests (folder-synchronized groups)
    DINCR/                     SwiftUI screens (App/, Features/, Resources/)
    DINCRUITests/              XCUITest flows on fixture data
    DincrKit/                  Swift package
      DincrCore                models, API client, Supabase PKCE auth, Keychain, formatting, fixtures
      DincrDesign              tokens (generated), components, charts
    Config/                    xcconfig + Info.plist (backend values only in Local.xcconfig)
  android/
    app/                       Compose app (screens, Keystore session store)
    core/data/                 pure Kotlin/JVM: models, API client, auth, formatting, fixtures
    core/design/               Compose theme, tokens (generated), components
```

## Build, run, test

Tokens:

```bash
node jarvis-personal/native/design-tokens/generate.mjs --check
```

iOS (Xcode 16+; builds use the full Xcode even when `xcode-select` points to the command line tools):

```bash
cd jarvis-personal/native/ios/DincrKit && DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
```

```bash
cd jarvis-personal/native/ios && DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild -project DINCR.xcodeproj -scheme DINCR -destination 'platform=iOS Simulator,name=iPhone 17' test
```

Android (JDK 17):

```bash
cd jarvis-personal/native/android && ./gradlew :core:data:test :app:assembleDebug
```

## Fixture mode and configuration

With no backend configured, both apps run on synthetic fixture data and show a "Modo de
demostración" banner. Scenarios: `populated`, `empty`, `failing`, `newUser`.

- iOS launch arguments: `-DincrFixtures <scenario>` and optionally `-DincrSkipLogin`.
- Android intent extras: `dincrFixtures=<SCENARIO>` and optionally `dincrSkipLogin=true`.

Live backend (never committed):

- iOS: copy `ios/Config/Local.xcconfig.example` to `ios/Config/Local.xcconfig`.
- Android: add `dincr.apiUrl`, `dincr.supabaseUrl`, `dincr.supabaseAnonKey` to
  `android/local.properties`.

OAuth uses the redirect `com.dincr.app://auth/callback`, already allowed for the Capacitor
app. The prototype uses its own app id (`com.dincr.app.nativedev`) so it never replaces the store
app. On a device that also has the Capacitor app installed, Android may ask which app opens the
callback; replacing `com.dincr.app` is a release decision.

## Known prototype limits

Tracked in `docs/native/PARITY_MATRIX.md` and `docs/design/reviews/R3-native-prototype.md`.
