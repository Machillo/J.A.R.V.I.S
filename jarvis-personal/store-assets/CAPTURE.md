# Capturing the raw screens

The store shows the **native DINCR app** (PR #287, merged into `main`). Captures are never taken
from the older Capacitor UI, never mocked, and never edited: `compose.mjs` refuses a capture from
before #287 or one whose SHA-256 no longer matches its manifest.

## Contract (what `compose.mjs --mode final` expects)

```
store-assets/raw/
  android/capture-manifest.json            written by scripts/capture-android.mjs
  android/<es|en>/phone/<screen-id>.png    emulator capture (1080x2400 on the reference emulator)
  ios/capture-manifest.json                written by scripts/capture-ios.mjs (MAC REQUIRED)
  ios/<es|en>/phone/<screen-id>.png        iPhone 6.9" simulator, 1320x2868
  ios/<es|en>/tablet/<screen-id>.png       iPad 13" simulator, 2064x2752 (while the app supports iPad)
```

Each manifest records: platform, fixture (`STORE`), fixture date, source commit, whether the tree
was clean, pipeline commit, capture time, app/build, device or simulators, status bar, and per
capture its screen, language, plan, file, SHA-256 and size.

## Data: the STORE fixture

- Debug builds only (the launch policy refuses fixtures in release). Android extras
  `dincrFixtures=STORE`, `dincrPlan=<plan>`, `dincrSkipLogin=true`, `dincrLatencyMs=0`; iOS arguments
  `-DincrFixtures store -DincrPlan free -DincrSkipLogin`.
- Invented person "Ana", mailbox `ana.demo@example.com`, a fictional "Mi banco / My bank" sender,
  amounts in colones (one dollar subscription). No real person, account, bank or statement.
- Fixed date 2026-09-28 (the second payday), six months of history, a plan bought in the store
  (no "courtesy" caption), a completed financial situation.
- Nothing the backend computes is invented. The strategy (Basic and VIP), the VIP command center
  (safe to spend, priority, alerts, roadmap, projections), the guided budget and the Free dashboard
  are the **backend engines' own output** for this account, in each language:
  `backend/tests/test_store_sample_engine.py` runs them on the account's data and pins the result in
  `native/android/core/data/src/main/resources/store-sample.json`; the Android fixture serves those
  responses as they are, and `StoreFixtureTest.kt` / `StoreSampleTests.swift` check that the
  fixtures' dashboards and debts equal them.
- Those outputs include the backend's current behaviour as it is (for example the VIP roadmap
  suggests investing because the command center does not read the emergency-fund target). A
  screenshot never corrects or embellishes it; a backend fix changes the golden file and the images.

## Android (automated; Windows, macOS or Linux)

Requirements: an emulator running (reference: Pixel 7 profile, API 35, 1080×2400, 420 dpi, Google
Play image), `adb`, JDK 17 in `JAVA_HOME`.

```bash
node jarvis-personal/store-assets/scripts/capture-android.mjs
```

It builds and installs the `dincr` Debug app and its test APK, then:

1. sets the device clock to 2026-09-28 09:41 (Costa Rica) so "Hoy/Ayer" labels match the data;
2. enables demo mode: 09:41, battery 100%, Wi-Fi full, no mobile type, no notifications;
3. for `es-CR` and `en-US` (per-app language) runs the opt-in test
   `app/src/androidTest/kotlin/com/dincr/app/StoreScreenshots.kt` (`storeScreenshots=true`), which
   launches the app with each screen's plan, navigates like a user, waits for the loaded content and
   saves the screen; any failed or skipped test aborts the run;
4. pulls the files into `raw/android/<es|en>/phone/`, checks their size and writes the manifest;
5. restores the device (automatic time as it was, demo mode off, app language reset).

Capture from a committed tree: a dirty `native/` or `store-assets/config/` is recorded and refused for finals.

## iOS — MAC REQUIRED

Not possible from Windows. On a Mac with Xcode 16 or later and an iOS 17+ simulator runtime, from
the repository root on this branch (or `main` after merge):

```bash
xcrun simctl list devices available | grep -E "iPhone 17 Pro Max|iPad Pro 13-inch"
node jarvis-personal/store-assets/scripts/capture-ios.mjs --phone "iPhone 17 Pro Max" --tablet "iPad Pro 13-inch (M4)"
```

| Item | Value |
|---|---|
| Simulators | iPhone 17 Pro Max (6.9", captures 1320×2868) and iPad Pro 13-inch (M4) (2064×2752). Any simulator with exactly those screen sizes works; the script refuses other sizes |
| Fixture | `-DincrFixtures store -DincrPlan free -DincrSkipLogin`, languages `(es)`/`es_CR` and `(en)`/`en_US` |
| Test | `DINCRUITests/StoreScreenshots.swift`, opt-in through `TEST_RUNNER_DINCR_STORE_SHOTS_DIR` (the script sets it) |
| Screens and navigation | `02-overview`: Hoy/Today tab · `03-movements`: Movimientos/Transactions tab · `04-debts`: Plan tab (debts, then goals) |
| Expected result | 12 PNGs: `raw/ios/<es\|en>/<phone\|tablet>/<02-overview\|03-movements\|04-debts>.png`, plus `raw/ios/capture-manifest.json`; status bar 9:41, full Wi-Fi and battery |
| Not captured on iOS | Home VIP, goals as a separate screen, budget, strategy, mail: the iOS app does not have them yet (`screens.json` gives the reason for each). The DINCR tab is an "under construction" screen and is never captured |

Equivalent manual command (what the script runs per device):

```bash
cd jarvis-personal/native/ios
xcrun simctl boot "iPhone 17 Pro Max"
xcrun simctl status_bar "iPhone 17 Pro Max" override --time 9:41 --dataNetwork wifi --wifiMode active --wifiBars 3 --cellularMode active --cellularBars 4 --batteryState charged --batteryLevel 100
TEST_RUNNER_DINCR_STORE_SHOTS_DIR="$(pwd)/../../store-assets/raw/ios" TEST_RUNNER_DINCR_STORE_DEVICE=phone \
  xcodebuild test -project DINCR.xcodeproj -scheme DINCR -destination "platform=iOS Simulator,name=iPhone 17 Pro Max" \
  -only-testing:DINCRUITests/StoreScreenshots CODE_SIGNING_ALLOWED=NO
```

Follow-up, on the same Mac (fonts: render the Apple set on one machine):

```bash
node jarvis-personal/store-assets/scripts/compose.mjs --mode final --targets apple-iphone-69,apple-ipad-13 --source-commit <source_commit from raw/ios/capture-manifest.json>
node jarvis-personal/store-assets/scripts/validate.mjs --targets apple-iphone-69,apple-ipad-13
```

Then look at every image, commit `raw/ios/` and `output/final/apple/` by name, and push to the PR.

Notes:

- The iOS simulator uses the Mac's clock, so the transactions list shows dates ("28 de
  septiembre") instead of "Hoy/Ayer" unless the Mac's date is 2026-09-28. Both are true to the data.
- iPad: the app declares iPhone and iPad (`TARGETED_DEVICE_FAMILY = 1,2`), so App Store Connect
  requires 13" iPad screenshots. Making the app iPhone-only is Kenneth's release decision; only
  then use `--no-tablet` and drop the `apple-ipad-13` target (`REQUIREMENTS.md`).
- The native iOS app is a partial prototype today (`native/RELEASE_IDENTITY.md`): 3 screenshots
  meet Apple's minimum of 1 but show a small part of the product.
- `capture-ios.mjs` and `StoreScreenshots.swift` have not run yet (no Mac here). CI compiles the UI
  test target when its iOS job finds a simulator; treat the first Mac run as their test.
