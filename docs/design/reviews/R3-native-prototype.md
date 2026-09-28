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
| N22 | `1,000` (dot_comma) / `1.000` (comma_dot) parsed as 1; no upper bound | important (financial) | max 2 decimals; ambiguity rejected. The 12-digit bound chosen here was wrong (revised by N33) | 21-case matrix per separator, identical on both platforms; mutation fails |
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

## Re-audit R3.2, 2026-09-28 (after syncing with main: #269, #272 and every earlier PR)

C4 is a **parallel prototype**: DINCR v1.0 ships the Capacitor app (`frontend`, `frontend/ios-dincr`,
`frontend/android`), which this PR does not touch. iOS 17 is the prototype's own target; the
releasable app and dincr.com stay on iOS 15. Contract re-checked against the FastAPI code on main
(`native/CONTRACT.md`). Android was built and tested locally (Windows, JDK 21 via a local-only
toolchain override; CI uses JDK 17). **Swift was not compiled locally** (no Mac): the iOS changes
are validated by the `Native apps` workflow only.

| # | Finding | Severity | Change | Test that prevents it |
|---|---|---|---|---|
| N33 | The amount input accepted 12 integer digits "for NUMERIC(14,2)", but every column it writes is `amount NUMERIC(12,2)` (`salaries`/`expenses`: the backend refuses more; `transactions`: the database would fail) | high (financial) | max 9 999 999 999.99 (10 integer digits + value bound), both platforms | `ReauditTest(s).amountLimitIsTheColumnOfEveryWrite` (max, one cent over, 1e30, 1e300, NaN, Infinity, non-ASCII digits); mutations killed |
| N34 | A row with `original_currency` equal to the base, or with only `original_amount`/`exchange_rate`, was editable; a `PUT` without `currency` erases `original_amount`/`original_currency`/`exchange_rate` of salary/expense rows (#269). Rows without a date were editable with "today" invented | high (financial) | any `original_*`/`exchange_rate` → read-only (edit and delete); no usable date → read-only; `exchange_rate` decoded | `rowsWithCurrencyDataOrNoDateAreReadOnly`; `writesNeverCarryACurrencyOrRate`; `untouchedAmountRoundTripsExactly` |
| N35 | Session race: a refresh of session A finishing after a sign-out or another sign-in was saved over the new session; a request of B could await A's refresh and receive A's token; a rejected refresh of A signed B out | high (isolation) | refresh keyed by refresh token; result saved only if the asking session is still current (`sessionChanged` otherwise) | `signOutDuringRefreshStaysSignedOut`, `anotherSignInDuringRefreshKeepsTheNewSession`, `anotherSessionNeverAwaitsTheOldRefresh`, `rejectedRefreshOfAnOldSessionDoesNotSignOutTheNewOne` |
| N36 | Android: cancelling the coroutine that was refreshing counted as a rejected refresh and signed the user out | medium | cancellation passes through; waiters get "offline" | `cancelledRefreshDoesNotSignOut` (iOS: `cancelledCallerDoesNotSignOut`) |
| N37 | Sign-out cleared the device session only after the network logout | medium | clear first, then tell Supabase | `signOutClearsBeforeTheNetworkCall` |
| N38 | Without backend configuration both apps ran on fixtures **in any build, Release included** (a sample account with invented balances) | blocker (fixtures reachable in Release) | `LaunchPolicy`: fixtures only in Debug and only when asked for; otherwise an "unconfigured" screen with no data | `releaseNeverRunsOnFixtures`, `missingConfigurationNeverFallsBackToFixtures`, `debugFixturesOnlyWhenAskedFor` |
| N39 | API/Supabase URLs were not required to be HTTPS | medium (network) | HTTPS required; HTTP only in Debug to loopback/emulator host; no credentials/query/fragment | `backendMustBeHttps` |
| N40 | HTTP redirects were followed (URLSession/OkHttp defaults) | medium (token replay) | redirects never followed; 3xx is an error | `transportFollowsNoRedirects` / `transportRefusesRedirects` |
| N41 | `check_public_secrets.py` did not scan `jarvis-personal/native` and missed `sb_secret_…` keys | medium | native tree scanned; new-format secret keys detected by value | planted probes in `native/` (assignment and `sb_secret_` value) fail the script |
| N42 | Token generator skipped malformed entries silently, defaulted the version to 0.0.0, accepted non-hex colors, duplicates and orphan dark tokens, and could not tell when a token the apps use disappeared | medium | strict parsing; `#RRGGBB`; duplicates/orphans/missing version fail; references in the apps must exist | `generate.test.mjs` (5 tests; `--check` proven not to write); 8/8 mutations killed |
| N43 | `native-ci.yml`: 3 jobs without timeout, no concurrency, third-party actions by tag, checkout kept credentials, Release never built, generator untested | medium (CI) | timeouts on every job, concurrency (cancel on PRs), `gradle/actions` and `android-emulator-runner` pinned to commit SHAs, `persist-credentials: false`, unsigned `assembleRelease` + `lintRelease`, `node --test` for the generator. Still `contents: read`, no secrets, no signing, no deploy | workflow run on this PR |
| N44 | `docs/native/PARITY_MATRIX.md` on main (#267, merged) lists D3/D4 as `POST /finance/income`, `PUT /finance/income/{id}`…: the real routes are `/user-product/finance/*` (create) and `PUT /user-product/free/movements/{id}` (the Movements edit used here) | low (docs debt) | documented; #267 not modified from this PR | — |
| N45 | Backend: the `transaction` origin of `PUT /free/movements` has no application-level amount bound (NUMERIC(12,2) overflow would be a database error) | low (out of scope, backend) | reported; the prototype never sends more than 9 999 999 999.99 | — |

Human/external gates unchanged: live OAuth needs `com.dincr.app.nativedev://auth/callback` in the
Supabase redirect allowlist (**not requested, not to be added for the prototype**); iOS rendering,
VoiceOver, Dynamic Type AX sizes and physical-device checks remain **HUMAN**.

### Independent adversarial review of R3.2 (security reviewer, read-only)

No blocker, no high. Findings and decisions:

| # | Finding | Severity | Decision / change | Test |
|---|---|---|---|---|
| N46 | Android: a cancelled caller dropped a refresh answer; Supabase had already rotated the token, so the device kept a spent refresh token (later sign-out) | medium | refresh and its recording run in `NonCancellable` (iOS already used an unstructured task) | `cancelledCallerStillRecordsTheRotatedToken` |
| N47 | iOS: `RefuseRedirects` is proven only as a delegate method, not wired through a live `URLSession` | medium | **open, needs a Mac**: a `URLProtocol` redirect test is the follow-up | — |
| N48 | Android: `loadIdentity` did not catch the new `SessionChanged` (crash in a narrow race) | medium | caught; any other error becomes an identity error, as on iOS | code review; Android build + UI tests |
| N49 | Any non-2xx/non-5xx refresh answer (3xx, 408, 429) signed the user out | low | only 400/401/403 end the session, both platforms | `transientRefreshAnswersKeepTheSession`, `rejectedGrantSignsOut` |
| N50 | Android: a request that read the session before another refresh saved could replay the spent refresh token | low | inside the lock: same account already rotated → use it; another account → `sessionChanged` | `aStaleReadUsesTheAlreadyRotatedSession`, `aStaleReadOfAnotherAccountNeverGetsItsToken` |
| N51 | A slow `/auth/me` could land after sign-out or another sign-in (name, formats, gates of the previous account) | low | session epoch in both AppModels | code review |
| N52 | README said a sign-in without the redirect allowlisted "fails visibly"; Supabase falls back to the Site URL | low | README corrected (the code is useless without the prototype's PKCE verifier) | — |
| N53 | Android Debug HTTP to `10.0.2.2` is accepted by the policy but blocked by the platform | low | documented (use HTTPS) | — |
| N54 | Stale comments (`Base.xcconfig` fixtures, CI "R8 keeps what the app needs"); column type wording | low | corrected | — |
| N55 | iOS Release configuration is never compiled in CI; the committed `gradle-wrapper.jar` relies on `setup-gradle` validation | low | open (CI follow-up) | — |
| N56 | Token generator accepted `0x10px`, negatives and a non-semver version inside string literals | low | `^\d+(\.\d+)?px$`, semver only | `generate.test.mjs` |
| N57 | Android `source_id` was 32-bit (`BIGSERIAL` ids above 2^31 would break decoding) | low | `Long` | build |
| N58 | `check_public_secrets.py` sees a legacy `service_role` JWT only under the named keys | low | open hardening (decode JWT role) | — |
