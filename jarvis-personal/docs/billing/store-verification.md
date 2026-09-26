# App Store and Google Play purchases

Paid plans (Basic, VIP) come only from purchases that Apple or Google confirm to the server. The app's word is never enough, and there is no off-store payment path. This document describes the backend implementation (`backend/product_ops/store_*.py`, migration `20260926160000_store_verification.sql`) and what humans must configure.

## Principles

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
- **Ordered and idempotent.**
  - A state with an earlier period end never overwrites a newer one. A refund or revocation always applies.
  - Every store event id is recorded once in `store_subscription_events`; a repeat returns `duplicate`.
- **No fake active purchase.**
  - Unknown product ids grant nothing.
  - Sandbox / test purchases grant nothing unless `DINCR_STORE_ACCEPT_SANDBOX=1`, for QA environments only.
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
| Refund / revoke | `revocationDate`, `REFUND` / `REVOKE` | voided purchase notification | `revoked` → Free; never reverts |
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
   - **Check** `store_apple.APPLE_ROOT_CA_G3_SHA256` against the certificate published at apple.com/certificateauthority. `DINCR_APPLE_ROOT_CA_SHA256` overrides it.
3. **Google:**
   - `FINVA_GOOGLE_PACKAGE_NAME`;
   - a service account with Play Console access "View financial data / manage orders and subscriptions", with its JSON in `DINCR_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (a secret);
   - a Pub/Sub topic for RTDN;
   - a **push** subscription to `/product-ops/billing/store/google/notifications` **with authentication**: a push service account in `DINCR_GOOGLE_RTDN_SERVICE_ACCOUNT` and an audience in `DINCR_GOOGLE_RTDN_AUDIENCE`.
4. **Scheduler:** call `POST /product-ops/billing/store/cron` hourly with `X-Cron-Secret: $DINCR_STORE_CRON_SECRET`.
5. **Migration:** apply `20260926160000_store_verification.sql` before deploying the code (`apply_migration.py`, BACKUP_VERIFIED).
6. **Existing sandbox rows:** production has simulator rows (provider `sandbox`) from QA. They never grant a plan, and the simulator is now off. Deleting them is a human decision (read-only check: `SELECT provider, status, count(*) FROM store_subscriptions GROUP BY 1, 2`).

## Not in this change (follow-up)

- **The purchase UI in the mobile app:**
  - StoreKit 2 / Play Billing via a Capacitor plugin;
  - passing the customer token;
  - sending the result to the verification endpoints;
  - "Restore purchases";
  - "Manage subscription" links.

  The backend is ready for it, but no device purchase has been tested.
- Store-side price and tax configuration, and the store review submissions.
