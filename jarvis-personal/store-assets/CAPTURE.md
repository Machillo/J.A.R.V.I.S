# Capturing the raw screens (POST-#287)

**Blocked until PR #287 (native DINCR app) is merged.** The store must show the UI that is
published. That UI is the native app, not the older Capacitor UI. Until then, do not capture or
approve finals. Nothing in this pipeline copies or depends on #287's unmerged code.

## Contract (what `compose.mjs --mode final` expects)

```
store-assets/raw/
  ios/capture-manifest.json           { "source_commit": "<sha on origin/main>", "app_version": "...", "fixture_scenario": "...", "captured_at": "..." }
  ios/<es|en>/phone/<screen-id>.png    iPhone 6.9" simulator capture (e.g. iPhone 17 Pro Max), status bar cleaned
  ios/<es|en>/tablet/<screen-id>.png   iPad 13" simulator capture (only while the app supports iPad)
  android/capture-manifest.json
  android/<es|en>/phone/<screen-id>.png  emulator capture, 1080 px wide or more
```

Screen ids come from `config/screens.json`. A screen can be used only after it is marked
`"confirmed": true`, with `how_to_reach` filled in, **after** checking that it exists in the
merged native app. If the app does not have a screen (for example Accounts), delete that entry;
never mock it. When the capture set is ready, set `release_gate.status` to `"released"`.

## Data rules

- Fixture mode only: iOS launch arguments `-DincrFixtures <scenario> -DincrSkipLogin`, Android
  extras `dincrFixtures`/`dincrSkipLogin`. These hooks exist in the native prototype on main and are
  **debug-only**. Confirm the scenario names in the merged app.
- Every name, amount, account and mailbox is invented. A demo mailbox is `ana.demo@example.com`.
- Before approving, look at every capture for anything real: names, emails, card digits, amounts copied from real statements.
- Status bars must be clean: full battery and signal, no carrier or notifications (Google policy). On iOS use
  `xcrun simctl status_bar <device> override --time 9:41 --batteryState charged --batteryLevel 100 --cellularBars 4 --wifiBars 3`.
  On Android enable demo mode (`adb shell settings put global sysui_demo_allowed 1`, then the `com.android.systemui.demo` broadcasts).

## iOS (Mac with Xcode)

1. Build the merged app in Debug and boot an iPhone 6.9" and an iPad 13" simulator.
2. Add a screenshot UI test in the native project (a separate PR, after #287). For each confirmed screen it should:
   - launch with the fixture arguments above and `-AppleLanguages (es)` / `(en)` plus the matching `-AppleLocale`;
   - navigate there with the same accessibility identifiers the existing UI tests use;
   - attach `XCUIScreen.main.screenshot()` with the screen id as its name.
3. Run the test with `xcodebuild test -scheme DINCR -destination 'platform=iOS Simulator,name=<device>' -resultBundlePath out.xcresult`.
4. Export the attachments (Xcode 16 or later) with `xcrun xcresulttool export attachments --path out.xcresult --output-path <dir>`, then copy them into the layout above.

## Android (Windows or Mac)

1. Build the merged app's debug APK and start an emulator (phone, 1080×2400 or larger). Enable demo mode for the status bar.
2. For each confirmed screen:
   - launch with `adb shell am start -n com.dincr.app.<flavor>/.MainActivity --es dincrFixtures <SCENARIO> --ez dincrSkipLogin true --el dincrLatencyMs 0`;
   - set the locale;
   - navigate there (instrumentation test or `adb shell input`);
   - capture it with `adb exec-out screencap -p > raw/android/<lang>/phone/<screen-id>.png`.

   An instrumentation test in the native project (after #287) is preferred for repeatability.

Write each `capture-manifest.json` with the commit the build came from. `compose.mjs --mode final`
refuses captures made from a commit that is not on `origin/main`.
