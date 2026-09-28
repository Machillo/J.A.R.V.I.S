# App Store and Google Play purchases

Paid plans (Basic, VIP) come only from purchases that Apple or Google confirm to the server. The app's word is never enough, and there is no off-store payment path. This document describes the backend implementation (`backend/product_ops/store_*.py`; migrations `20260926160000_store_verification.sql` (expand) and `20260926161000_store_verification_activation.sql` (activation)), how it is rolled out, and what humans must configure.

## Principles

- **Off until a human turns it on.** Every store verification path answers 503 unless `DINCR_STORE_VERIFICATION_ENABLED=1` (exactly `1`; unset, empty or any other value is off). The check is the router's first dependency and the first statement of every entry point, before any database access, so a deploy of this code is inert. See [Rollout](#rollout).

- **Verified, never asserted.**
  - Apple purchases and notifications are JWS objects. A signature counts only when its x5c chain ends in the pinned *Apple Root CA - G3* (`store_apple.py`).
  - Google purchases are read from the Play Developer API with DINCR's service account (`store_google.py`). A Google notification only triggers a fresh read, and its Pub/Sub push must carry Google's OIDC token for DINCR's push identity.
- **One purchase, one account, forever.**
  - Each account gets a random store customer token (`store_customer_tokens`). The app passes it as StoreKit `appAccountToken` / Play `obfuscatedAccountId`. A verified purchase carrying that token belongs to that account.
  - A purchase without a token (bought before this change, or restored) belongs to the first authenticated account that presents it.
  - Presenting a purchase from another account is refused with 409 and recorded in `store_purchase_conflicts` (account ids only).
- **Per-purchase truth, derived entitlement.**
  - `store_purchases` keeps the latest verified state of every purchase. Keys: Apple `originalTransactionId`; Google the SHA-256 of the purchase token, never the token itself.
  - The account's `store_subscriptions` row, and its self-service plan in `account_subscriptions`, come from the best live purchase: VIP over Basic, then the later end. This covers a user who has both an Apple and a Google subscription.
  - With no live purchase, the plan falls back to Free.
  - Owner and courtesy access are never touched.
- **Ordered, per transaction, idempotent.**
  - A state about an older store transaction never replaces a newer one:
    - Apple compares the transaction's purchase date, so a renewal or an upgrade wins even with an earlier period end;
    - Google always uses a fresh API read.
  - About the same transaction, the latest store statement wins (`observed_version`: Apple's `signedDate`, Google's API read time). A late Apple retry therefore cannot undo a newer grace or refund.
  - Upgraded Apple transactions (`isUpgraded`) are ignored.
  - One purchase and one account are processed at a time (transaction advisory locks).
  - Every notification id is recorded once in `store_subscription_events`; a repeat returns `duplicate`. A repeated Google notification still acknowledges a live, unacknowledged purchase, so a failed acknowledgement is retried.
- **Refunds are per transaction** (`store_revocations`, kept even when the account is deleted):
  - a refunded past renewal does not end a later paid one;
  - a refund of the current transaction ends the plan;
  - that transaction's pre-refund receipt, presented again, stays refunded;
  - a later paid renewal restores the plan;
  - Apple `REFUND_REVERSED` restores it.
- **The client can confirm, never end.** A purchase the app presents can activate or extend a plan. Expiration and grace come only from store notifications and the lapse cron. An app re-presenting an old receipt during billing retry therefore cannot drop a paying user to Free. The one exception is a refund: a store-signed revocation applies even when the app delivers it.
- **No fake active purchase.**
  - Unknown product ids grant nothing.
  - Sandbox / test purchases grant nothing, with two exceptions:
    - `DINCR_STORE_ACCEPT_SANDBOX=1`, for QA environments only;
    - accounts listed in `DINCR_STORE_SANDBOX_ACCOUNT_IDS`, for example the App Store review account. App Review buys in Sandbox against the production server, so it needs this; TestFlight users are not listed.
  - Family-shared Apple purchases and non-subscription products grant nothing.
  - The Owner lifecycle simulator is off unless `DINCR_STORE_SIMULATOR=1`, and its rows (provider `sandbox`) never count as a store entitlement.

## Lifecycle

| Situation | Apple | Google | DINCR state |
|---|---|---|---|
| Purchase / renewal | transaction, `expiresDate` in the future | `SUBSCRIPTION_STATE_ACTIVE` | `active` until the period end |
| Free trial | `offerType = 1` (free trial) | offer tagged `free-trial` | `trialing` until its end |
| Cancelled, still paid | `autoRenewStatus = 0`, not expired | `SUBSCRIPTION_STATE_CANCELED`, not expired | `active` (`auto_renew = false`) until the period end |
| Billing retry with grace | `gracePeriodExpiresDate` in the future | `SUBSCRIPTION_STATE_IN_GRACE_PERIOD` | `grace_period` until the store's grace end (`grace_ends_at`) |
| On hold / pending payment | expired, no grace | `ON_HOLD`, `PENDING` | `expired` (no access) |
| Expired | `expiresDate` passed | `SUBSCRIPTION_STATE_EXPIRED` | `expired` → Free |
| Refund / revoke | `revocationDate`, `REFUND` / `REVOKE` (`REFUND_REVERSED` undoes it) | voided order notification | that transaction is `revoked`; if it is the current one → Free, until a later paid transaction |
| Upgrade | new transaction for the higher product | new token with `linkedPurchaseToken` | new purchase applies; Google's old token becomes `superseded` |
| Downgrade at renewal | `autoRenewProductId` differs | new token at renewal | shown as `pending_plan_code` until it takes effect |
| Restore on a new device | the app sends the transaction again | the app sends the token again | same purchase, same account |
| No notification arrives | — | — | `POST /product-ops/billing/store/cron` recomputes lapsed accounts |

In `store_subscriptions`, `current_period_end` is the **entitlement end**: the grace end while in grace. Readers can therefore compare that one column. The store's exact dates are kept in `store_purchases`.

## Endpoints

All live under `/product-ops/billing/store`.

| Path | Who | Purpose |
|---|---|---|
| `POST /customer-token` | signed-in user | The token to pass to the store before buying (created once, then returned) |
| `POST /apple/transactions` | signed-in user | After a purchase or restore: StoreKit 2 `jwsRepresentation` |
| `POST /google/purchases` | signed-in user | After a purchase or restore: `purchaseToken` and `productId`. The server acknowledges it |
| `POST /apple/notifications` | Apple (public, JWS-verified) | App Store Server Notifications V2 |
| `POST /google/notifications` | Pub/Sub push (public, OIDC-verified) | Real-time developer notifications |
| `POST /cron` | scheduler (`X-Cron-Secret`) | Recompute entitlements that ended without a notification |

## HUMAN-ONLY configuration

Nothing here is in the repository.

1. **Products.** Create in App Store Connect and Play Console the subscription products whose ids match `FINVA_{BASIC,VIP}_{MONTHLY,ANNUAL}_PRODUCT_ID`, or set those variables to the ids used.
2. **Apple:**
   - `FINVA_APPLE_BUNDLE_ID`;
   - App Store Server Notifications **V2**, production URL → `/product-ops/billing/store/apple/notifications`;
   - `DINCR_APPLE_ENVIRONMENTS=Production` (add `Sandbox` only in a QA environment).
   - **Check** `store_apple.APPLE_ROOT_CA_G3_SHA256` against the certificate published at apple.com/certificateauthority. It is a constant: no setting can replace it.
3. **Google:**
   - `FINVA_GOOGLE_PACKAGE_NAME`;
   - a service account with Play Console access "View financial data / manage orders and subscriptions", with its JSON in `DINCR_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (a secret);
   - a Pub/Sub topic for RTDN;
   - a **push** subscription to `/product-ops/billing/store/google/notifications` **with authentication**: a push service account in `DINCR_GOOGLE_RTDN_SERVICE_ACCOUNT` and an audience in `DINCR_GOOGLE_RTDN_AUDIENCE`.
4. **Scheduler:** call `POST /product-ops/billing/store/cron` hourly with `X-Cron-Secret: $DINCR_STORE_CRON_SECRET`.
5. **Migrations and the switch:** follow [Rollout](#rollout). Never set `DINCR_STORE_VERIFICATION_ENABLED` before both postflights are clean.
6. **Existing sandbox rows:** production has simulator rows (provider `sandbox`) from QA. They never grant a plan, and the simulator is now off. Deleting them is a human decision (read-only check: `SELECT provider, status, count(*) FROM store_subscriptions GROUP BY 1, 2`).

## Rollout

Merging this code can deploy it at once, while production migrations are applied separately (from the Mac, with `apply_migration.py`, which only applies a file identical to `origin/main`). The main CI also forbids granting `dincr_app` a table its code does not use. So the code lands first, **switched off**, and the schema follows in two migrations:

| State | What is true | Store verification |
|---|---|---|
| A. Before merge | old code; neither migration | does not exist |
| B. Merged and deployed | new code; `DINCR_STORE_VERIFICATION_ENABLED` unset; neither migration | 503 on every store path, no access to the new schema; everything else unchanged |
| C. `20260926160000` applied (expand) | four `store_*` tables and three `store_subscriptions` columns; RLS on; no privilege for `anon`, `authenticated` or `dincr_app`; no policy | still 503 |
| D. `20260926161000` applied (activation) | `dincr_app` has exactly the privileges the code runs, the conflict-id sequence USAGE and one `dincr_app_access` policy per table | **still 503**: a migration never turns it on |
| E. A human sets `DINCR_STORE_VERIFICATION_ENABLED=1` on every backend service | | working |

Steps:
1. Merge (the PR's PRE-MERGE GATE: the `migration-gate-acknowledged` label). Do not set the switch.
2. Mac: backup (BACKUP_VERIFIED), then apply `20260926160000`. Its postflight must return zero rows.
3. Mac: apply `20260926161000` (it refuses to run before 160000: `SV004`). Its postflight must return zero rows.
4. Configure the stores and secrets (HUMAN-ONLY configuration above).
5. Only now set `DINCR_STORE_VERIFICATION_ENABLED=1`.

`test_store_verification_rollout_pg.py` walks states B to E with this code as `dincr_app`.

### Failure and rollback
- **Deployed, migrations not applied (yet or at all):** leave the switch off. Nothing else depends on the new schema.
- **160000 fails:** it runs in one transaction and changes nothing. Leave the switch off; fix, and re-apply after a new review.
- **161000 fails:** it changes nothing (one transaction; `SV002` / `SV004` abort before any grant). Leave the switch off. The expand state (C) is safe to keep.
- **A postflight returns rows:** leave the switch off and investigate; do not work around it.
- **Switched on too early (before 161000):** the store paths fail closed with "permission denied" and write nothing. Unset the switch.
- **Turning it off after activation:** unset the switch. The data stays and nothing is read or written.
- **Rolling back the schema:** switch off first, then `database/rollback/20260926161000_store_verification_activation_rollback.sql` (takes back the grants and policies, keeps the data; the 160000 postflight is then clean again), then, only if there is no history to keep, `database/rollback/20260926160000_store_verification_rollback.sql` (refuses with `SV003` while the activation is in place, `SV001` while any purchase, refund, conflict or token row, or any new `store_subscriptions` column value, exists).

## Decisions for a human

- **Resubscribing from another DINCR account with the same Apple ID or Google account.** The purchase stays bound to its first account: the new account gets 409 and a conflict record, although the store charged. Support resolves it; there is no automatic transfer. Change this policy only deliberately (for example, "the token wins for a new transaction after the old one expired").
- **App Review:** list the review account in `DINCR_STORE_SANDBOX_ACCOUNT_IDS`, and add `Sandbox` to `DINCR_APPLE_ENVIRONMENTS`, only while a review is open.

## Entitlement reader

`has_store_entitlement` (`product_ops/service.py`) is the only reader of a store entitlement. This change only writes the `store_subscriptions` row it reads, including the grace end. The off-store billing tables are retired (`20260926152000`).

## Mobile client

The app (`frontend/src/lib/storeBilling/`, UI in `src/users/components/StoreSubscriptionPanel.jsx`) buys through the stores with the plugin `@capgo/native-purchases` (pinned version; StoreKit 2 on iOS, Play Billing Library 9 on Android, Swift Package Manager). It never grants a plan: the plan shown is always the backend's (`GET /auth/me`; `GET /billing/store/entitlement` only describes the store subscription).

**Purchase** (Settings → "Suscribite con App Store / Google Play", native app only, `user` role only):
0. **One store subscription at a time.** If `GET /billing/store/entitlement` shows a live App Store or Google Play subscription, the app does not open the store again. It points to "Gestionar suscripción" instead: the plugin cannot replace a Play subscription in-app, so a second purchase would be billed alongside the first. Changing plan or period is done in the store. On iOS, all four products must be in **one subscription group**.
1. `POST /billing/store/customer-token`. A 503 here (store verification off) stops the flow **before the store opens**: nothing is charged. The token is the account's UUID, used as is.
2. The store purchase:
   - iOS: `Product.purchase` with `appAccountToken` = the token;
   - Android: `launchBillingFlow` with `setObfuscatedAccountId` = the token and the base plan returned by Play (a base plan named `monthly` / `annual` is preferred). The plugin reports Android subscriptions one entry per offer, with `planIdentifier` = the product id and `identifier` = the base plan id; the regular price shown is the base plan's.
3. The evidence goes to the backend:
   - iOS: the transaction's `jwsRepresentation` → `POST /apple/transactions` `{signed_transaction}`;
   - Android: the purchase token and product id → `POST /google/purchases` `{purchase_token, product_id}`.
   Only DINCR's catalog products (`GET /billing/store/catalog`) are accepted; a malformed store result is not sent.
4. The app reloads `/auth/me` and `/billing/store/entitlement` and shows what the backend says.

Prices, currency and period text come from the store (`getProducts`), never from the backend catalog, which only maps product → plan → period.

**Who finishes what** (no race between the device and the backend):
- **Google Play:** only the backend acknowledges, after verifying (`store_verification.verify_google_purchase`). The device passes `autoAcknowledgePurchases: false` on every plugin call and never calls the plugin's `restorePurchases` on Android, because that call acknowledges every purchase. An unverified purchase therefore stays unacknowledged, and Google refunds it after 3 days, instead of charging for a plan DINCR refused.
- **App Store:** the device finishes a transaction only after a definitive backend answer (verified, 409 or 422). Unfinished transactions stay in StoreKit's current entitlements. StoreKit's own update listener (renewals, Ask to Buy) finishes updates and triggers a recovery.

**Restore** ("Restaurar compras"):
- iOS: `AppStore.sync()`, then every current entitlement's JWS;
- Android: every current subscription purchase from `queryPurchases`.

The store is read first. With no DINCR purchase there, restore ends: it requests no customer token and calls no verification endpoint (as recovery does). Otherwise it requests the customer token. A 503 (store verification off) ends it, and no evidence is sent.

Each purchase then goes to the backend, which decides ownership. A 409 (the purchase belongs to another DINCR account) changes nothing on the device and shows a message without ids.

**Recovery when the store charged but DINCR did not answer** (network down, app killed, backend 5xx or 503, kill switch still off): nothing is stored on the device; the store keeps the evidence. After the store charged, any non-final answer shows "la reintentaremos", never "not available". On login and on every app resume (`App.jsx` → `recoverStorePurchases`), the app sends again this account's purchases that the backend has not answered yet:
- Android: purchased and not acknowledged. This includes a backend answer of `acknowledgement: "pending"` and a 422, which on Google can be a temporary Play API failure;
- iOS: current entitlements not answered in this app session. An Apple 422 (signature not verifiable) is final.

With nothing bought in the store, recovery makes no backend call. In particular, it creates no customer token.

Pending payments (Google pending purchase, Apple Ask to Buy) are sent once the store reports them purchased.

**Never on the device:** store secrets or service accounts; logging, analytics or local storage of JWS / purchase tokens; the offline operation queue (store paths are not recoverable operations); purchases on the web (no store buttons there, the plugin is never invoked).

**Kill switch:** while `DINCR_STORE_VERIFICATION_ENABLED` is off, the panel shows "Las compras desde la app todavía no están disponibles" and offers no purchase. Free, courtesy and Owner access are unaffected.

**Known plugin behaviour** (not DINCR code; see the PR):
- **Android logcat:** the Android plugin writes the purchase token (and `Purchase.toString()`) to logcat at debug/info level during a purchase. Release builds keep those logs (`minifyEnabled false`). Only adb, bug reports or privileged apps can read logcat. A leaked token cannot be claimed by another DINCR account (409), because the purchase is bound to its `obfuscatedExternalAccountId`. Removing the lines needs an R8 rule or a plugin patch (a human decision).
- **Capacitor logging:** in debug builds, Capacitor's default logging prints plugin results.
- **iOS finishing:** on iOS the plugin's `Transaction.updates` listener finishes updates (and transactions re-delivered at launch) before DINCR sees them. That costs no money: Apple does not refund unfinished transactions. Active subscriptions are recovered from current entitlements, and anything else from App Store Server Notifications.
- **Calls DINCR avoids on Android:** `isBillingSupported`, `getStorefront`, `restorePurchases` and `consumePurchase` open a billing client that auto-acknowledges; the test forbids them.

**Not validated:** a purchase on a device (sandbox / license tester); the iOS build, which needs the Mac (Xcode resolves the Swift package).

## Not in this change (follow-up)

- The App Store Server API (`Get All Subscription Statuses`, which needs an API key) would let the server re-read Apple's state instead of relying on notifications between renewals. Google tokens are not stored, so Google state between notifications relies on RTDN and on the app re-verifying.

- No device purchase has been tested yet (see [Mobile client](#mobile-client) → not validated).
- Store-side price and tax configuration, and the store review submissions.
