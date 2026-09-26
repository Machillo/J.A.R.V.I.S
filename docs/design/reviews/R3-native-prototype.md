# Review R3 — Native prototype (C4), 2026-09-26

Targets: `jarvis-personal/native/ios` (SwiftUI) and `jarvis-personal/native/android` (Compose):
Login, Profile setup, Home (Free overview), Movements, add/edit/delete movement, Profile.
Checklists applied: Impeccable `audit.native.md` (5 dimensions), `ios.md`, `android.md`, craft floor
(commit `9d715cc`); UI/UX Pro Max `pro-rules.md` pre-delivery checklist and SwiftUI / Compose
stack rules (commit `dcc40ff`). Native code has no Impeccable detector (it reads HTML/CSS only).

## Verification evidence

| Check | iOS | Android |
|-------|-----|---------|
| Unit tests (contract fixtures, money formatting/parsing, API client retry/refresh/errors, PKCE RFC 7636 vector, session refresh) | `swift test`: 28 tests pass | `:core:data:test`: 24 tests pass |
| Build | `xcodebuild` Debug, iPhone 17 simulator (iOS 27): succeeds, 0 warnings | `:app:assembleDebug`: succeeds |
| Static analysis | Swift 6 strict concurrency, 0 warnings | Android lint: 0 errors (was 18 `NewApi`) |
| UI flows on fixture data | XCUITest: 6/6 pass (login→home, home sections, add expense with validation, empty, failing backend, profile setup) | `scripts/smoke.sh` (adb + uiautomator): 6/6 pass (login without Apple, home figures and spoken labels, empty, failing, profile setup) |
| Accessibility tree audit | via XCUITest queries | touch targets ≥ 48 dp and labels on every clickable: Home 0, Movements 0 (after fix), Editor 0 issues |
| Rendered review | iPhone 17: Login (light), Home (dark) reviewed | Home tree reviewed via uiautomator |

## Findings

| # | Source | Finding | Severity | Decision | Change | Re-audit |
|---|--------|---------|----------|----------|--------|----------|
| N1 | Own check (emulator accessibility tree) | Spoken money used display grouping ("257.550 colones"); English screen readers read it as a decimal | **blocker** (wrong money read aloud) | Accepted | Spoken form uses ungrouped digits and the language's decimal mark, both platforms; regression tests | PASS (unit tests + emulator tree `plus 865000 colones`) |
| N2 | Android lint `NewApi` | `java.time` crashes on API 24–25 (minSdk 24, parity with Capacitor) | **blocker** | Accepted | Core library desugaring | PASS (lint 0 errors) |
| N3 | Impeccable audit.native (labels) / UI/UX Pro Max `aria-labels` | Android "Add" FAB exposed no accessible name (NAF node) | important | Accepted | Explicit extended FAB with content description | PASS (audit 0 issues) |
| N4 | Own check (data integrity) | Amount input accepted "1,5" in comma_dot as 15 | important | Accepted | Strict grouping parser on both platforms, UI test covers "1.5.2" | PASS |
| N5 | UI/UX Pro Max "Correct Brand Logos" | Google button used an SF Symbol "G"; Apple button not Apple-styled | important | Accepted | Official Google "G" + Google branding colors; Apple black/white style | PASS (iOS login screenshot) |
| N6 | Impeccable ios.md (platform controls) | Transient feedback must not be a toast on iOS | important | Accepted | In-place result + haptic + inline status row + VoiceOver announcement | PASS |
| N7 | Own check (XCUITest stall) | Looping skeleton pulse kept the app from idling (also energy) | moderate | Accepted | `dincrDecorativeMotion` environment; off under Reduce Motion and in UI tests | PASS |
| N8 | Visual review | Chart legend crowded the top axis label | polish | Accepted | Legend spacing | pending re-capture |
| N9 | Impeccable audit.native (Adaptivity) | iPad sidebar (`sidebarAdaptable`) needs iOS 18; baseline proposal is iOS 17 | moderate | Deferred | Tab bar on iPad until the baseline decision | open (human decision) |
| N10 | UI/UX Pro Max (charts) | Android income/expense chart has no table alternative (iOS has one) | moderate | Open | Module work | open |
| N11 | Native tech | Android Compose instrumented tests cannot see the UI in the Compose test environment on this emulator (tree empty), although the app renders correctly | moderate | Open | Tests kept in `app/src/androidTest`, excluded from CI; adb smoke script used instead | open |
| N12 | Localization | Prototype copy uses `tx(es, en)` like the web | moderate | Open | Move to String Catalog / `strings.xml` in module work | open |
| N13 | Android lint (icons) | Launcher icons reused from Capacitor: no monochrome (themed) icon | polish | Open | Asset work | open |
| N14 | Platform | Native Sign in with Apple (AuthenticationServices) instead of the web OAuth flow needs Supabase Apple provider client-id configuration | moderate | Open | Agent A / human config | open |

## Human-only

- Real Google/Apple OAuth round trip (needs `Local.xcconfig` / `local.properties` with the Supabase project values, and a device).
- Face ID / fingerprint are not part of this prototype (App lock is parity A12–A13, module work).
- Physical-device feel: haptics, Dynamic Type on hardware, Android back gesture.

## Not validated

- iOS screenshots for Movements, Profile setup, AX5 Dynamic Type and English were captured but not reviewed:
  the image-reading tool was unavailable in this session. Re-review before C4 is merged.
