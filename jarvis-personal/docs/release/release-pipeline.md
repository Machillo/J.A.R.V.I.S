# DINCR release pipeline: preparation (human gates marked)

Nothing here signs, uploads or publishes anything. Every account, certificate, payment and store action is a **HUMAN GATE**.

## 1. Version identity

- `npm run release:version` (from `jarvis-personal/frontend`) shows Android and iOS side by side and fails if they differ.
- `npm run release:version -- 1.10.0` sets `versionName`/`MARKETING_VERSION` on both platforms and moves both build numbers to `max + 1`. Stores reject a repeated or lower build number.
- The web bundle takes its version from Android's `versionName` (`vite.config.js`), and the release policy compares against that same number. Before this change iOS was behind (1.9.7/32 vs 1.9.11/36), so it has been aligned to 1.9.11 (36).
- CI now runs `npm run test:release-identity`.

## 2. Android: AAB for Play

1. **HUMAN GATE:** create the upload keystore once, and store it and its passwords outside the repository in a password manager:
   ```bash
   keytool -genkeypair -v -keystore dincr-upload.jks -alias dincr-upload -keyalg RSA -keysize 2048 -validity 10000
   ```
   Enrol in **Play App Signing**: Google keeps the app signing key; this key only uploads.
2. Put the four values in `~/.gradle/gradle.properties` on the build machine, or in environment variables. Never commit them:
   `DINCR_UPLOAD_STORE_FILE`, `DINCR_UPLOAD_STORE_PASSWORD`, `DINCR_UPLOAD_KEY_ALIAS`, `DINCR_UPLOAD_KEY_PASSWORD`.
   `android/app/build.gradle` signs the release build only when they exist. Without them, `bundleRelease` produces an **unsigned** AAB, which is useful only to check that the build works. Verified locally.
3. Build:
   - `npm run build`, then `npx cap sync android`;
   - `android/gradlew bundleRelease` (on Windows inside OneDrive, use the mirror from `npm run android:apk`);
   - the output is `android/app/build/outputs/bundle/release/app-release.aab`.
4. Include `google-services.json` for Firebase (git-ignored), and set `VITE_POSTHOG_KEY`/`VITE_POSTHOG_HOST` only once the PostHog human gates are cleared (see `docs/analytics/posthog-event-taxonomy.md`).

## 3. iOS: archive for App Store Connect (Mac + Xcode, HUMAN)

1. `npm ci`, then `npm run ios:sync`. That builds with `com.dincr.app` and syncs `ios-dincr`, and the script checks the bundle id and the onboarding bundle.
2. In Xcode:
   - select the Apple Developer team;
   - set automatic signing for `com.dincr.app`;
   - check the Associated Domains and Sign in with Apple capability;
   - then Product → Archive, and Distribute → App Store Connect → TestFlight.
3. Prerequisite: the **Apple provider must be enabled in Supabase** (today it is off; see `docs/security/supabase-auth-password-surface.md`). Otherwise the "Continue with Apple" button fails in review.
4. Pending from the store audit: revoking the Apple token on account deletion (guideline 5.1.1(v)) needs the team `.p8` key.

## 4. Future CI (proposal, not enabled)

- **Android:** a manual `workflow_dispatch` job on `ubuntu-latest` that decodes the keystore from a GitHub **environment secret** requiring approval, then runs `bundleRelease` and uploads the AAB as an artifact. Publishing stays manual, or goes through the Play API only after approval.
- **iOS:** needs macOS runners plus App Store Connect API keys. Start by keeping it manual.
- **Secrets never live in the repository.** `backend/scripts/check_public_secrets.py` already runs in CI.

## 5. Google Play Console checklist (HUMAN)

- Developer account (organisation vs personal; the D-U-N-S number if organisation). A new personal account has closed-testing requirements: **verify the current rule** in the Play Console Help Center.
- App: `com.dincr.app`. The package name is permanent after the first upload.
- **Data safety.** Must match reality: email (auth), financial info, app activity (PostHog), crash logs (Crashlytics), identifiers (the Firebase `setUserId` finding in #210), and Gmail data processed server-side.
- **Financial features declaration.** Personal finance management, no lending. Verify the current form.
- Account deletion: the in-app flow plus the public `/delete-account` URL.
- **Gmail restricted scope (`gmail.readonly`):** Google OAuth verification plus a possible **CASA security assessment** before public use. Verify the status in Google Cloud Console.
- Content rating, target audience (18+), privacy policy URL, store listing and screenshots, reviewer access (a demo account via `seed_review_demo`).
- Pricing: in-app subscriptions must use Play Billing when sold inside the app. Verify current policy before enabling payments.

## 6. App Store Connect checklist (HUMAN)

- Apple Developer Program membership, then the App ID `com.dincr.app` with Sign in with Apple.
- App Privacy details (same data inventory as Data Safety), the privacy policy URL, and the in-app account deletion guideline.
- Sign in with Apple is required alongside Google (4.8). Configure the Supabase provider first.
- Reviewer notes: the demo account, Gmail connection explained, and the statement that DINCR gives no financial advice.
- In-app purchases/subscriptions go through StoreKit when sold in the app. Verify current guidelines and any external-link entitlements.
- The minimum Xcode/SDK version required for submission. Verify at submission time.

## 7. Before charging the first customer: Costa Rica tax and invoicing (VERIFY WITH OFFICIAL SOURCES)

The items below list **what must be verified**, not current legal requirements. Confirm each one with the Ministerio de Hacienda (official site) and a Costa Rican accountant before charging.

- [ ] **Registration.** Register as a taxpayer for the digital-service economic activity, including the correct activity code. Check which Hacienda platform is currently in force for registration and filing.
- [ ] **Electronic invoicing.** Check whether and how DINCR must issue electronic receipts (comprobantes electrónicos) for each type of sale:
  - direct sales, if any are made outside the stores;
  - store payouts, where Google/Apple are the buyer of record in many markets;
  - also check the version of the receipt format currently in force.
- [ ] **VAT (IVA) on digital services.** Establish who charges and remits it when the sale happens through Google Play or the App Store (the store as merchant of record) versus a direct sale, and the rate applicable to DINCR's service.
- [ ] **Store payouts.** Find out how income from Google/Apple (in foreign currency) is invoiced and declared, and whether that counts as an export of services.
- [ ] **Alegra** (if chosen as the e-invoicing provider):
  - HUMAN: create the account, link it to Hacienda (credentials and cryptographic key), and set up economic activities, products/services and numbering;
  - never put Alegra or Hacienda credentials in this repository or in the frontend;
  - integration code does not exist yet and is **post-launch** unless direct sales are planned for v1.
- [ ] **Consumer and privacy.** Check whether any Costa Rican consumer-protection disclosures for subscriptions (renewal, cancellation) apply. The privacy policy must name every processor: PostHog, Firebase, OpenAI (Owner-only, not Users), Microsoft, Google and Supabase.

Record each verification with its date and source link. Do not charge until every box is checked.
