# Native DINCR — release identity (pending decisions)

The native apps can run against the real backend, but **shipping them in place of the Capacitor
app is a release decision that has not been made.** This file lists everything that changes when
the native app takes the store identity, and what must exist first. Nothing here has been done:
no console, store, Supabase or backend setting was changed by the native RC.

## Identities today

| Build | Android id | iOS bundle | Auth redirect | Mail return deep link | Use |
|-------|------------|------------|---------------|-----------------------|-----|
| Capacitor (store app) | `com.dincr.app` (versionCode 36, 1.9.11) | `com.dincr.app` (iOS 15) | `com.dincr.app://auth/callback` | backend setting, default `com.finva.app://gmail/callback` | Production |
| Native `dincr` flavor | `com.dincr.app` (versionCode 100, 2.0.0-rc.1) | — | `com.dincr.app://auth/callback` | claims `com.dincr.app` and `com.finva.app` `…/gmail/callback` | Test RC (debug-signed) |
| Native iOS app | — | `com.dincr.app` (2.0.0, build 100, iOS 17) | `com.dincr.app://auth/callback` | claims `com.dincr.app` and `com.finva.app`; the mail session waits for `com.finva.app` | Release identity, unsigned in CI |
| Native Android `nativedev` flavor | `com.dincr.app.nativedev` | — | `com.dincr.app.nativedev://auth/callback` | own scheme only | Side-by-side development (Android only) |

## What happens if the `dincr` RC APK is installed on a phone

- It **replaces** a Capacitor debug build of `com.dincr.app` (same id, same debug key, higher
  versionCode). Against a Play-installed Capacitor app the install fails with a signature
  mismatch: uninstall it first (this deletes its local data).
- The user must **sign in again**: the Capacitor session lives in the WebView's storage, which the
  native app does not read. Local preferences (theme, app lock, dismissed notices) start over.
- Anything still in the **Capacitor offline write queue** (WebView storage) is not sent by the
  native app. Before replacing it, open the Capacitor app online once so the queue flushes.
- Live Google sign-in returns to `com.dincr.app://auth/callback`, the redirect the Capacitor app
  already uses in production (so it is in the Supabase allowlist; not re-verified in the
  dashboard). `nativedev` sign-in does **not** work live: its
  redirect is not in the allowlist and must not be added to production for testing.
- Mail connections return to the backend's global return URL. The `dincr` flavor claims both
  `com.dincr.app` and the legacy `com.finva.app` `…/gmail/callback` links, so it receives the
  return the backend sends today (the Capacitor app claims the same three links). Both apps use
  the same id, so they are never installed together and no link chooser appears.
- Store purchases do not work in this APK: Play Billing needs a build distributed by Google Play.

## Pre-release gates (all human, none done)

### Android (Google Play)

1. **Signing.** Build the release with the upload key the Play Console expects for `com.dincr.app`
   (Play App Signing). The RC APK is debug-signed and cannot be uploaded.
2. **Version.** `versionCode` must be greater than the last published Capacitor code (the RC uses
   100). Decide the public `versionName` (the RC says `2.0.0-rc.1`).
3. **Billing.** Products in the Play Console must match the ids the backend catalog returns; the
   backend's Google package setting must be `com.dincr.app`; verify with a license-tester account
   on an internal track (the app never grants a plan itself — the backend verifies every token).
4. **Mail return.** Decide the final return URL (`com.dincr.app://gmail/callback` vs the legacy
   `com.finva.app://gmail/callback`). Changing the backend setting affects every installed app at
   once, so it must happen together with a release where all clients claim the new link.
5. **Data safety / privacy labels** reviewed for the native app (biometrics are local only; no
   analytics beyond allow-listed screen names).
6. **Staged rollout** on an internal/closed track first; keep the Capacitor build ready to roll back
   (a rollback needs a higher versionCode than the native build).

### iOS (App Store) — requires a Mac

The code already carries the release identity: bundle `com.dincr.app` (`Config/Base.xcconfig`,
pinned by `IdentityGuardTests`), UI tests `com.dincr.app.uitests`, version 2.0.0 build 100 (above
the Capacitor build 36), auth redirect `com.dincr.app://auth/callback`, URL schemes `com.dincr.app`
and `com.finva.app`, Face ID text (ES/EN) and a privacy manifest. What only a person can do:

1. **Signing.** Set the team (`DEVELOPMENT_TEAM`) in Xcode for the `DINCR` target; automatic signing
   with the existing App ID `com.dincr.app`. Nothing is committed for it.
2. **Capabilities.** None are required by this build: Google and Apple sign-in run as Supabase web
   OAuth in `ASWebAuthenticationSession` (as in Capacitor, which has no entitlements file). A native
   Sign in with Apple button would need the capability plus Supabase `signInWithIdToken` — not built.
3. **Minimum iOS — decision.** The native app targets **iOS 17**; the Capacitor app supports **iOS 15**.
   - iOS 17 comes from: Observation (`@Observable`, `@Environment(Type.self)`), `.sensoryFeedback`,
     the two-parameter `onChange`, `LocalAuthentication` `.opticID`.
   - iOS 16 would need replacing Observation with `ObservableObject` in every screen and the
     haptics/onChange calls: feasible, but it touches every view and gives no functional gain.
   - iOS 15 would also lose `NavigationStack`, Swift Charts, `presentationDetents`,
     `webAuthenticationSession` (16.4) and `Task.sleep(for:)`: it needs UIKit bridges and a
     different navigation model — a serious degradation, not recommended.
   - Impact: devices that cannot run iOS 17 (iPhone 8/8 Plus/X) would stay on the last Capacitor
     build. Recommendation: **keep iOS 17**; keep the Capacitor build available until the decision.
   - When decided, update dincr.com `landing/config.json` `minimumOS` (checked by `test:landing`).
4. **App Store Connect.** Version 2.0.0, privacy labels matching `PrivacyInfo.xcprivacy` (email,
   name, financial info, emails for the opt-in Email Monitor; no tracking), review notes for the
   Email Monitor (read-only Gmail).
5. **Purchases.** App Store subscriptions are not built (StoreKit products and App Store Connect
   configuration first); the plan screen says they come later.
6. **Replacing Capacitor.** The Capacitor session and its offline queue live in the WebView and are
   not migrated: users sign in again; ship after a Capacitor build has flushed its queue.
   **Capacitor fallback retained until physical native iOS acceptance.**

### Backend and Supabase

- No migration, secret or endpoint change is required by the native RC.
- No Supabase change is required for the `dincr` flavor or the iOS app: both use
  `com.dincr.app://auth/callback`, which the Capacitor app already uses (verify it is still in
  Supabase Auth → URL Configuration → Redirect URLs; not verified from the repository).
  Adding the Android `nativedev` redirect to the production allowlist is **not** requested.
- **Apple provider.** Continuing with Apple works only if the Supabase Apple provider is enabled for
  production (same as the Capacitor app today; not verifiable from the repository).
- **Gmail OAuth.** The Google Cloud OAuth client and its consent screen stay as they are: the backend
  asks only for `gmail.readonly` (pinned by backend tests and by DincrKit `EmailMonitorTests`).
  `FINVA_GMAIL_REDIRECT_URI` (the backend callback) does not change. The app return is the global
  `FINVA_GMAIL_RETURN_URL`; the iOS session waits for `com.finva.app`, the current default. If that
  setting moves to `com.dincr.app://gmail/callback`, update `AppModel.mailCallbackScheme` in the
  same release.

## Checklist before a native build reaches users

- [ ] Kenneth decides the native app replaces Capacitor on Android (and when).
- [ ] Release signing with the Play upload key; versionCode/versionName decided.
- [ ] Physical-device pass (see the PR's Android physical-test list).
- [ ] Mail return URL decision and coordinated backend setting change (if any).
- [ ] Billing verified on an internal track with a license tester.
- [ ] iOS: signing team, iOS 15 vs 17 decision, App Store Connect record/labels and a device pass on a Mac
      (the bundle id and redirect are already the release ones in code).
