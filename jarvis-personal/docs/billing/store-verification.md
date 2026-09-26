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
- **Ordered, per transaction, idempotent.**
  - A state about an older store transaction never replaces a newer one:
    - Apple compares the transaction's purchase date, so a renewal or an upgrade wins even with an earlier period end;
    - Google always uses a fresh API read.
  - Updates about the same transaction always apply.
  - Upgraded Apple transactions (`isUpgraded`) are ignored.
  - One purchase and one account are processed at a time (transaction advisory locks).
  - Every notification id is recorded once in `store_subscription_events`; a repeat returns `duplicate`.
- **Refunds are per transaction** (`store_revocations`, kept even when the account is deleted):
  - a refunded past renewal does not end a later paid one;
  - a refund of the current transaction ends the plan;
  - that transaction's pre-refund receipt, presented again, stays refunded;
  - a later paid renewal restores the plan;
  - Apple `REFUND_REVERSED` restores it.
- **The client can confirm, never end.** A purchase the app presents can activate or extend a plan. Expiration, grace and refunds come only from store notifications and the lapse cron. An app re-presenting an old receipt during billing retry therefore cannot drop a paying user to Free.
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
5. **Migration:** apply `20260926160000_store_verification.sql` before deploying the code (`apply_migration.py`, BACKUP_VERIFIED).
6. **Existing sandbox rows:** production has simulator rows (provider `sandbox`) from QA. They never grant a plan, and the simulator is now off. Deleting them is a human decision (read-only check: `SELECT provider, status, count(*) FROM store_subscriptions GROUP BY 1, 2`).

## Decisions for a human

- **Resubscribing from another DINCR account with the same Apple ID or Google account.** The purchase stays bound to its first account: the new account gets 409 and a conflict record, although the store charged. Support resolves it; there is no automatic transfer. Change this policy only deliberately (for example, "the token wins for a new transaction after the old one expired").
- **App Review:** list the review account in `DINCR_STORE_SANDBOX_ACCOUNT_IDS`, and add `Sandbox` to `DINCR_APPLE_ENVIRONMENTS`, only while a review is open.

## PRE-MERGE dependency

On `main`, access to Basic and VIP features still comes from `has_active_payment`, which reads the off-store billing tables, and from the launch-promotion expiry code, which ignores stores. #257 replaces both with `has_store_entitlement`, which reads the `store_subscriptions` row this change maintains, including the grace end.

**Merge #257 first.** Otherwise a store-paid Basic or VIP user gets 402, and a courtesy user who buys drops to Free when the courtesy ends.

## Not in this change (follow-up)

- The App Store Server API (`Get All Subscription Statuses`, which needs an API key) would let the server re-read Apple's state instead of relying on notifications between renewals. Google tokens are not stored, so Google state between notifications relies on RTDN and on the app re-verifying.

- **The purchase UI in the mobile app:**
  - StoreKit 2 / Play Billing via a Capacitor plugin;
  - passing the customer token;
  - sending the result to the verification endpoints;
  - "Restore purchases";
  - "Manage subscription" links.

  The backend is ready for it, but no device purchase has been tested.
- Store-side price and tax configuration, and the store review submissions.
