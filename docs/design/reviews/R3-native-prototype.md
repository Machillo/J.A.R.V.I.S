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

## Final audit (R3.1), 2026-09-26

Checked against the FastAPI code on `main` (contract in `jarvis-personal/native/CONTRACT.md`) and
the #267 parity matrix. Impeccable and UI/UX Pro Max were **not installed** in this environment and
were not re-run; the review below is a manual pass with their R3 checklists plus a rendered check on
an Android emulator (API 35). iOS changes were validated by CI only (no Mac in this session).

| # | Finding | Severity | Change | Evidence |
|---|---|---|---|---|
| N15 | `/auth/me` returns `id` as an integer; both clients decoded a string, so identity never loaded against the real backend (fixtures hid it) | **blocker** | `Profile.id` Int/Long; fixtures rebuilt from `enrich_identity` | contract tests + mutation (String id → test fails) |
| N16 | Editing a movement prefilled the rounded display value (₡18.450,5 → "18.450") and saved it, rewriting the amount even when only the description changed | **blocker** (financial truth) | `inputText` exact prefill; untouched amount sent as stored | unit round-trip tests; Android UI test `editKeepsTheStoredAmountAndCategory` fails with the old prefill |
| N17 | Editing silently replaced a category outside the fixed list with the first option | important | stored category stays selectable | same UI test (iOS twin added) |
| N18 | Android: a rejected session refresh (`AuthException.SignedOut`) or any non-`ApiError` crashed Home, Movements, the editor and onboarding | important | `AppModel.load` maps failures; sign-out instead of crash | code review; unit + UI tests green |
| N19 | Android double tap could submit create/profile setup twice (state set inside the launched coroutine) | important | synchronous single-flight guard + `X-Idempotency-Key` on creates (both platforms, as the Capacitor app) | unit tests: header sent, writes never retried, fixture replays the key |
| N20 | OAuth callback accepted any URL starting with the redirect (`…/callbackX`), and shared `com.dincr.app://auth/callback` with the store app (Android chooser / collision) | important (security) | exact scheme/host/path, no fragment/userinfo/port, exactly one code; own scheme `com.dincr.app.nativedev`; redirect via a forwarding `AuthCallbackActivity` | 12 rejected-URL cases per platform; mutation (prefix match) fails |
| N21 | Android exported launcher activity honoured the `dincrFixtures` extra in any build: another app could show DINCR with fake balances | important (security) | launch fixtures only in Debug builds (both platforms) | code review |
| N22 | `1,000` (dot_comma) / `1.000` (comma_dot) parsed as 1; no upper bound | important (financial) | max 2 decimals, max 12 integer digits (NUMERIC(14,2)); ambiguity rejected | 21-case matrix per separator, identical on both platforms; mutation fails |
| N23 | Spoken amount ignored the row currency; Kotlin spoke "EUR" where iOS said "euros"; display rounding half-even vs the web's half-up | moderate | spoken currency override; same units; half away from zero | unit tests |
| N24 | Basic/VIP users saw the Free overview with no notice; `plan_selected` null opened the app (Capacitor gates on `!plan_selected`) | moderate | notice on Home; gate on `!= true` | code review |
| N25 | Home empty state could never show against the real backend (it always sends six zero-filled months) | moderate | empty = all months zero | fixture now mirrors the backend |
| N26 | Deleting an already-deleted movement / editing a removed one showed an error and left the list stale | moderate | 404 → refresh + notice | fixture 404 semantics + unit test |
| N27 | Swift mapped a cancelled `URLSession` task to "Sin conexión" | minor | `CancellationError` passes through | unit test |
| N28 | Android chart month labels clipped at 200 % font scale | moderate (a11y) | chart height no longer fixed | emulator screenshot at font scale 2.0 |
| N11 | Compose instrumented tests "could not see the UI" | resolved | root causes: `singleTask` moved MainActivity out of the ActivityScenario task, and tests forced `Locale.setDefault` which Android resets at launch. `singleTop` + forwarding callback activity; locale-independent tests | 8/8 on API 35 emulator locally; CI job on API 24 and 35 |
| N29 | Token generator crashed on CRLF checkouts (Windows `core.autocrlf`) | minor | normalizes line endings | `--check` passes on a CRLF checkout |
| N30 | Search was case-sensitive to accents ("credito" ≠ "Crédito") | minor | presentation-only accent/case folding | unit tests |
| N31 | Android tab labels truncate at 200 % font ("Trans…") | minor | Material 3 behaviour; revisit with navigation work | screenshot |
| N32 | Pre-existing backend: an editable manual `transaction` with type `debt_payment` is listed as `expense`, and a PUT writes `expense` back (Capacitor has the same bug) | out of scope | reported, not changed | backend `free_service.py` |

Rendered on Android (API 35 emulator): Login, Home light/dark, Home at font scale 2.0, Movements,
edit sheet. iOS renders were not reviewed in this session: **HUMAN VISUAL GATE** for iOS.
