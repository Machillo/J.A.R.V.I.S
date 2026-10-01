# DINCR native apps (release candidate)

Native DINCR for Android (Kotlin + Jetpack Compose) and iOS (Swift + SwiftUI), on the same
FastAPI contract as the Capacitor app ([CONTRACT.md](CONTRACT.md)). Feature status per platform is
in `docs/native/PARITY_MATRIX.md`.

- **Android** is the functional RC: sign-in, legal and plan gates, profile setup, Free/Basic/VIP
  home, movements (CRC/USD with the user's own rate), debts, goals, savings plans, budget,
  calendar, recurring, strategy, scenarios, VIP review/today/projections, mail monitor (connect,
  sync, review, own transfers, accounts), financial situation, plans and store subscription,
  app lock, export, account deletion, support, kill switches, release policy and service health.
- **iOS** has the same scope with the release identity `com.dincr.app`: gates, Free/Basic/VIP home,
  movements in CRC/USD, planning (debts, goals, savings, budget, calendar, recurring, emergency,
  aguinaldo), advisor (strategy, scenarios, review, Today, projections, reports), financial
  situation, plans, app lock, export, deletion, support, and the **Email Monitor** (Gmail read-only:
  consent, connect, return, sync, review, own transfers, detected accounts). It is compiled and
  tested in CI on a macOS runner (unit tests and XCUITest in a simulator); it has not run on a
  device yet (MAC/DEVICE REQUIRED list in the PR and `RELEASE_IDENTITY.md`).

## Status: RC, not yet the store app

- DINCR in the stores is still the **Capacitor app** (`jarvis-personal/frontend`, native shells
  `frontend/ios-dincr` and `frontend/android`). The native apps never modify it.
- Taking the store identity is a pending human decision: see [RELEASE_IDENTITY.md](RELEASE_IDENTITY.md)
  (signing, versionCode, mail return URL, billing, iOS 15 vs 17, session not migrated).
- Android has two flavors: `dincr` (`com.dincr.app`, the redirect the Capacitor app already uses)
  and `nativedev` (`com.dincr.app.nativedev`, side-by-side, fixtures or a development project).
- **iOS 17 is the native app's own deployment target.** The Capacitor iOS app and dincr.com stay on
  iOS 15 until that decision is made. Android `minSdk` is 24 in both.

## Rules

- **Business logic stays in FastAPI.** Native code presents, navigates and integrates with the
  platform. It never computes financial results; every figure on screen is a backend value.
  Client-side calculations found in Capacitor are listed in
  `docs/native/CURRENT_STATE_AUDIT.md` §5 as backend dependencies.
- **Same API contract as the web client**: bearer token, `Accept-Language`, stable
  `X-Request-ID`, retries only for safe methods, one token refresh on 401, 20 s timeout.
- **Owner boundary**: the Owner (a server role, never a plan) uses the public app at VIP level and,
  on top of it, JARVIS, its personal space (Profile → JARVIS; `Jarvis.swift` / `Jarvis.kt`). Only
  the role in `/auth/me` shows it; the backend still decides every request (`/jarvis/*` keeps its
  historical owner + admin access for the web Owner app, but the native JARVIS UI is Owner-only). JARVIS
  sections are ported step by step (JARVIS recovery roadmap; the chat since J1, `JarvisChatSession`,
  session-only history, changes saved only after Confirmar; the agenda since J2, the next 45 days of
  events, created only through the chat via "Agendar con JARVIS"); until then each one says it is being
  restored. Free, Basic and VIP never see it; an admin session sees a notice and no app. The Owner's
  strategy comes from `/jarvis/premium/strategy-dashboard` (his historical JARVIS inputs) and his
  "Análisis financiero" JARVIS section from the Owner finance routes; VIP users use the neutral
  `/vip/strategy-dashboard` and `/vip/salvavidas` (the backend runs the Owner's personal rules only for the
  server Owner role). Plan holds Aguinaldo, Estrategia, Salvavidas and Distribución; Cuentas reviews the
  same mail candidates as Correos. `/vip/debt-advisory` is not used.
- **Reads do not write.** Opening a screen never calls a write (no lifecycle snapshot POST). One
  documented exception, Owner only: the historical `GET /finance/net-worth` keeps one derived
  net-worth snapshot per day (an upsert for its history chart; no balance, debt or transaction changes).
- **Money.** `BigDecimal`/`Decimal` only; every amount is positive, ≤ 2 decimals and ≤
  9,999,999,999.99 (NUMERIC(12,2)); exchange rates are the user's own (> 0, never fetched or
  invented); creates carry an idempotency key reused only when the same submission is retried.
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
cd jarvis-personal/native/android && ./gradlew :core:data:test :app:assembleDebug :app:assembleRelease :app:lintNativedevDebug :app:lintDincrRelease
```

Compose flows on a running emulator or device (CI runs them on API 24 and 35):

```bash
cd jarvis-personal/native/android && ./gradlew :app:connectedNativedevDebugAndroidTest
```

Test APK of the `dincr` identity (debug-signed, live backend; needs the Supabase values below):

```bash
cd jarvis-personal/native/android && ./gradlew :app:assembleDincrDebug
```

## Fixture mode and configuration

Fixture (synthetic) data runs **only in a Debug build and only when asked for**, with a "Modo de
demostración" banner. On Android it is an in-process fake backend (`FakeBackend`, an HTTP
transport answering the real routes with invented data); on iOS `FixtureBackend`, the same idea.
Scenarios: `populated`, `empty`, `failing`, `newUser`, legal required, plan choice, and on iOS
`mailOnboarding` (a VIP mailbox to connect: consent → connect → return → sync).

- iOS launch arguments: `-DincrFixtures <scenario>` (`legalRequired`, `choosePlan`…),
  optionally `-DincrSkipLogin` and `-DincrPlan basic|vip`.
- Android intent extras: `dincrFixtures=<SCENARIO>` (`LEGAL_REQUIRED`, `CHOOSE_PLAN`…),
  optionally `dincrSkipLogin=true` and `dincrPlan=BASIC|VIP`, or `dincr.fixtures=true` in
  `android/local.properties` (Debug only).
- A Release build ignores all of them (Android's launcher activity is exported, so another app
  could send the extras): it can never be pointed at sample data.

Without a backend configuration, both apps stop at an **"App sin servidor configurado"**
screen; they never fall back to fixtures silently. Live backend (never committed):

- iOS: copy `ios/Config/Local.xcconfig.example` to `ios/Config/Local.xcconfig`.
- Android: add `dincr.supabaseUrl` and `dincr.supabaseAnonKey` (and optionally `dincr.apiUrl`;
  the `dincr` flavor defaults to the production API) to `android/local.properties`, or the
  `DINCR_SUPABASE_URL` / `DINCR_SUPABASE_ANON_KEY` / `DINCR_API_URL` environment variables.
- Both URLs must be HTTPS (plain HTTP only in Debug, only to loopback or the emulator's
  `10.0.2.2`). Only the Supabase anon/publishable key belongs here, never a server key.

OAuth (Supabase PKCE S256, system browser: `ASWebAuthenticationSession` on iOS, Custom Tabs on
Android, never a WebView) returns to the identity's own redirect: `com.dincr.app://auth/callback`
for iOS and the Android `dincr` flavor (the redirect the Capacitor app already uses), and
`com.dincr.app.nativedev://auth/callback` for the Android `nativedev` flavor. The `nativedev` redirect is not
in the production allowlist and must not be added for testing; without it, Supabase falls back to
the Site URL and the flow ends outside the app (the authorization code is useless there, because
only the app holds its PKCE verifier).

Android note: the platform blocks cleartext HTTP (targetSdk 36, no network security exception), so
a Debug build pointed at `http://10.0.2.2` is accepted by `LaunchPolicy` but its requests fail as
"offline". Use HTTPS (for example a tunnel) for a local backend.

## Known limits

Tracked in `docs/native/PARITY_MATRIX.md` (rows not `PASS`), [RELEASE_IDENTITY.md](RELEASE_IDENTITY.md)
and `docs/design/reviews/R3-native-prototype.md`.
