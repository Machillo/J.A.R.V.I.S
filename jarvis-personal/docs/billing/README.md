# Billing: App Store and Google Play only

**Product decision:** DINCR sells Basic and VIP only through the stores: StoreKit on iOS and Google Play Billing on Android. There is **no off-store payment**: no SINPE Móvil, no bank transfers, no uploaded receipts, no manual orders and no Owner-approved payments.

## What grants a paid plan

- **A store subscription** in `store_subscriptions` from a real store (`apple` or `google`) while it is `trialing` (until `trial_ends_at`), `active` or `grace_period` (until `current_period_end`). See `product_ops.service.has_store_entitlement`.
  - `sandbox` rows come from the Owner-only QA simulator and **never** grant access.
  - Known gap, tracked with the store verification work: real store grace periods run *after* `current_period_end`, so they need their own stored end.
- **A courtesy** (`account_subscriptions.access_source = 'courtesy'`), such as the launch promotion, until its `expires_at`. When the promotion ends, the account keeps the plan only if a live store subscription backs it; otherwise it returns to Free.
- **Owner** is internal and never purchasable.

Nothing else grants a paid plan. Until server-side store verification ships, `create_checkout` answers 503 outside the promotion rather than issuing any other kind of order.

## Retired off-store schema

| Table | Held | State when retired |
|---|---|---|
| `billing_orders` | SINPE orders and receipts | empty |
| `billing_subscriptions` | off-store paid periods | empty |
| `finva_beta_programs` | paid-beta configuration | one configuration row, no personal data |

- **Migration:** `database/migrations/20260926120000_retire_offstore_billing.sql`. It aborts (SQLSTATE `BL001`) and drops nothing if any order or subscription exists, or more than the configuration row.
- **Rollback:** `database/rollback/20260926120000_retire_offstore_billing_rollback.sql` recreates the three tables empty, plus a configuration row with default values.
  - **Apply it BEFORE reverting the code.** Older code reads `billing_subscriptions` on every `/auth/me` and fails without it.
  - It is not needed to revert only the code while the migration has not run.
- **Order:** deploy the code first (it no longer reads these tables), then apply the migration with the protocol in `docs/security/migration-safety-protocol.md`. The old code reads these tables, so the migration must never run before the deploy.
- **Guard:** `backend/test_security_contract.py::test_dincr_takes_no_off_store_payment` fails if runtime code references the retired tables or functions, or exposes an order or receipt route.

SINPE also appears in the **bank-notification parsers**. Those read a user's own bank emails about their own transfers; that is financial data, not billing, and stays.
