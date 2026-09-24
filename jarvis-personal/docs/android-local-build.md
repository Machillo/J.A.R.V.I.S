# Local Android debug APK

From `jarvis-personal/frontend`:

```bash
npm ci                       # once, or after package-lock changes
npm run android:apk          # web build → cap sync android → Gradle assembleDebug
npm run android:apk -- --check   # only validate prerequisites
```

The APK ends up at `frontend/android/app/build/outputs/apk/debug/app-debug.apk`. Install it with `adb install -r <path>`.

## What the script checks (fails with a message)

- Node 20+ (brace-expansion and other dev tooling require it).
- A JDK 17+: `JAVA_HOME`, falling back to Android Studio's bundled JBR.
- The Android SDK: `ANDROID_HOME` / `ANDROID_SDK_ROOT` / `android/local.properties` / the default install path.
- `node_modules` installed, Supabase URL and anon key present in `.env`, and `capacitor.config.json` is `com.dincr.app`.
- `google-services.json` (optional):
  - To include it, set `GOOGLE_SERVICES_JSON=<path>`. The script checks that it contains `com.dincr.app` and copies it into `android/app`, which git ignores.
  - Without it, the APK still builds, but Firebase Analytics/Crashlytics are disabled.
- Backend used by the APK: native builds call `VITE_NATIVE_API_URL` if set, otherwise **production** (see `src/lib/apiUrl.js`). The script says which one.

It never prints `.env` values and never commits anything.

## Windows + OneDrive

When the repo lives in OneDrive, Gradle fails with `Cannot snapshot …\node_modules\…: not a regular file`, because OneDrive turns files into cloud placeholders (reparse points).

The script detects OneDrive and handles it:
- it runs Gradle on an incremental `robocopy` mirror of `android/` and `node_modules/` in `%LOCALAPPDATA%\DINCR\android-build` (override with `DINCR_ANDROID_BUILD_DIR`);
- it then copies the APK back to the usual path.

The first mirror takes about 30–60 s; later runs only copy changes. `--in-place` skips the mirror. The permanent fix is to keep the repository outside OneDrive, for example `C:\dev\J.A.R.V.I.S`.

`npx cap sync android` rewrites `android/app/capacitor.build.gradle` and `android/capacitor.settings.gradle` with LF endings. `android/.gitattributes` pins them to LF, so a sync on Windows (`core.autocrlf=true`) no longer shows phantom modifications.

## Out of scope

This script builds debug only. Release AAB/APK builds need the upload keystore, which is never stored in the repository (see the release checklist). macOS/Linux use `sh gradlew`, because `gradlew` is committed without the executable bit. iOS builds use `npm run ios:sync` / `ios:open` plus Xcode.
