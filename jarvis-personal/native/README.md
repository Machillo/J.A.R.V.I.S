# DINCR native apps (prototype)

Native DINCR for iOS (Swift + SwiftUI) and Android (Kotlin + Jetpack Compose). This is the
**representative prototype** (phase C4): login, profile setup, Home (Free overview), Movements,
add/edit/delete movement, profile/appearance/sign-out. The Plan and DINCR tabs are "under
construction" screens with their parity IDs; legal consent and plan selection route to a notice;
Basic and VIP users see the Free overview with a notice. Most of the product (debts, goals, mail,
billing, app lock, push, settings, support) is not started. The backend contract the apps use is
in [CONTRACT.md](CONTRACT.md).

## Status: a parallel prototype, not the release app

- DINCR **v1.0 ships the Capacitor app**: `jarvis-personal/frontend` with its native shells
  `frontend/ios-dincr` (iOS) and `frontend/android` (Android). This prototype never modifies them.
- The prototype is **not** a release candidate, not a replacement for Capacitor, and not the
  source of truth for the bundle id, the minimum OS versions or store metadata. It is never
  distributed. A native migration is a decision for after v1.0, once parity is sufficient
  (`docs/native/PARITY_MATRIX.md`).
- **iOS 17 is the prototype's own deployment target** (SwiftUI APIs it uses). The releasable iOS
  app stays on iOS 15 (`ios-dincr`), and dincr.com keeps publishing iOS 15 (`landing/config.json`
  `minimumOS`, checked by `test:landing` against `ios-dincr`). Android `minSdk` is 24 in both.
- Its own ids (`com.dincr.app.nativedev`, UI tests `com.dincr.app.nativedev.uitests`) and its own
  OAuth redirect never collide with the store app's `com.dincr.app`.

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
cd jarvis-personal/native/android && ./gradlew :core:data:test :app:assembleDebug :app:lintDebug
```

Compose flows on a running emulator or device (CI runs them on API 24 and 35):

```bash
cd jarvis-personal/native/android && ./gradlew :app:connectedDebugAndroidTest
```

## Fixture mode and configuration

Fixture (synthetic) data runs **only in a Debug build and only when asked for**, with a "Modo de
demostración" banner. Scenarios: `populated`, `empty`, `failing`, `newUser`.

- iOS launch arguments: `-DincrFixtures <scenario>` and optionally `-DincrSkipLogin`.
- Android intent extras: `dincrFixtures=<SCENARIO>` and optionally `dincrSkipLogin=true`, or
  `dincr.fixtures=true` in `android/local.properties` (Debug only).
- A Release build ignores all of them (Android's launcher activity is exported, so another app
  could send the extras): it can never be pointed at sample data.

Without a backend configuration, both apps stop at a **"Prototipo sin servidor configurado"**
screen; they never fall back to fixtures silently. Live backend (never committed):

- iOS: copy `ios/Config/Local.xcconfig.example` to `ios/Config/Local.xcconfig`.
- Android: add `dincr.apiUrl`, `dincr.supabaseUrl`, `dincr.supabaseAnonKey` to
  `android/local.properties`.
- Both URLs must be HTTPS (plain HTTP only in Debug, only to loopback or the emulator's
  `10.0.2.2`). Only the Supabase anon/publishable key belongs here, never a server key.

OAuth (Supabase PKCE S256, system browser: `ASWebAuthenticationSession` on iOS, Custom Tabs on
Android, never a WebView) returns to the prototype's own development redirect
`com.dincr.app.nativedev://auth/callback`, so it can never receive or steal the store app's
`com.dincr.app://auth/callback`. **External gate, not requested:** live sign-in would need that URL
in Supabase Auth → URL Configuration → Redirect URLs. It is not in the production allowlist and
must not be added for this prototype; without it the Supabase sign-in fails visibly (no silent
fallback). Taking over `com.dincr.app` is a release decision that this prototype does not make.

## Known prototype limits

Tracked in `docs/native/PARITY_MATRIX.md` and `docs/design/reviews/R3-native-prototype.md`.
