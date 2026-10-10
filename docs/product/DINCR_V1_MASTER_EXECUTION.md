# DINCR v1: master execution record

The living record of DINCR v1's technical completion. It is kept on the branch `v1/master-execution-doc` and updated in that same PR as each block advances. Once merged, later updates go through new PRs from `main`.

- **What it records:** what is done, how it was verified, what is blocked and by whom, and how to resume.
- **What it does not replace:**
  - the approved decisions in `DINCR_UX_RESTRUCTURE_PROPOSAL.md` (frozen copy) and `README.md` (later decisions);
  - the reachability contract `jarvis-personal/native/feature-reachability.json`.

Evidence paths are relative to `jarvis-personal/` unless they start with `docs/` or `.github/`. "Verified" means seen in the code at the stated commit, or a test run on that commit. Production state (applied migrations, Render, Supabase, store consoles, crons) is **not visible from the repository** and is never stated as fact here.

## 1. Last verified state

| Item | Value |
|---|---|
| `main` | `984a2325` (2026-10-09), merge of #351 |
| Open PRs (others) | #319: single-owner roles migration (P0.2d phase 3), waiting for authorization. #304: PostHog analytics contract, conflicting with `main` since 2026-10-01 |
| Last merged blocks | #348 B17 pull to refresh · #349 E04/E05 summary charts · #350 UNKNOWN ≠ 0 on the planning screens · #351 a paid subscription needs a known end on every server path |
| Backend tests at `main` | 2,736 passed (`pytest backend`, embedded PostgreSQL) + 140 `labs` |
| Native tests at `main` (local, API 36 + iPhone simulator) | iOS DincrKit 322, iOS UI 117 (116 passed, 1 skipped). Android unit 306, Android UI 113 (8 skipped, StoreScreenshots) |

## 2. Owner decisions recorded here

Approved by Kenneth on 2026-10-09 (V1 closing brief) and in the V1 master prompt. They are added to the earlier decisions; none of those is deleted. Where one changes an earlier statement, the earlier one is named.

| # | Decision | Earlier statement it changes or confirms |
|---|---|---|
| V1-1 | The official apps are native iOS (Swift) and Android (Kotlin). Capacitor is not the store client | Confirms UX-10/11 (#333). Closes the open "release decision" in `native/RELEASE_IDENTITY.md`. `CLAUDE.md §1` still says "via Capacitor" (to update in a reviewed PR) |
| V1-2 | Payments through Apple StoreKit and Google Play Billing, verified by the backend | Consistent with `docs/billing/README.md` (store-only) |
| V1-3 | Direct commercial launch, with no mandatory public or closed beta. Internal and physical tests stay mandatory | — |
| V1-4 | Manual entry plus automatic detection from Costa Rican banks' emails in validated formats | UX-2, B3 |
| V1-5 | For Free, Basic and VIP, every movement detected by email needs the user's confirmation before it affects balances | Already the Users behavior (`user_product/gmail_service.py:508-593`) |
| V1-5a | **Owner is not a commercial plan.** Owner keeps its exclusive automation (`auto_commit`, learned rules, automatic classification). The confirmation rule does not apply to Owner. Owner behavior is not changed without explicit authorization | Supersedes the proposal in #351's report to remove the Owner's `auto_commit` (withdrawn) |
| V1-6 | Complete every planned financial function of Free, Basic and VIP before the commercial launch (not an MVP) | — |
| V1-7 | Accounts: declared opening balance, an estimated balance from confirmed movements, reconciliation, estimated ≠ verified | P2.8a/b/c, K-3/P0.9 |
| V1-8 | Health: a 0–100 score. **Formula, weights and thresholds NOT approved** | K-2/P3.7 |
| V1-9 | Projections: base, favorable and unfavorable scenarios, plus simulations. Estimates are never shown as certainties | UX-14 |
| V1-10 | Full debt management: payments, interest, due dates, partial and extra payments, history, reconciliation. A due installment is not a payment | K-4, P2.2, P2.6 |
| V1-11 | Planning: budgets by category, fixed expenses, calendar, savings goals, emergency fund, alerts | — |
| V1-12 | In-app and native push notifications, configurable, private, without duplicates | New: the current module is Owner-only web push |
| V1-13 | Free = essential management; Basic = planning; VIP = advanced analysis. Exact entitlements follow the existing contracts | `auth/saas.py:28-46` |
| V1-14 | No artificial limits on movements, accounts or debts by plan; reasonable technical controls only | — |
| V1-15/16 | Balanced prices. The initial market is Costa Rica only; the main currency is CRC | — |
| V1-17 | Monthly and annual subscriptions. **Annual discount and annual prices NOT approved** | — |
| V1-18 | Monthly prices: **Basic ₡2.990, VIP ₡5.990** | The code, the landing page and the terms still say VIP ₡4.990 (see BLK-PRICE) |

## 3. Inventory

**States:**
- COMPLETED_AND_VERIFIED
- IMPLEMENTED_NOT_VERIFIED
- PARTIALLY_IMPLEMENTED
- NOT_IMPLEMENTED
- BLOCKED_BY_DECISION
- BLOCKED_BY_MIGRATION
- BLOCKED_BY_EXTERNAL_SERVICE

"Verified" in this table means automated tests on both platforms where the function exists in both, and backend tests for its contract. **No function has a physical device pass yet**, so nothing is release-verified.

**Column legend:**
- **Plans:** F = Free, B = Basic, V = VIP, O = Owner.
- **Pri:** P0 / P1 / P2.
- **Mig:** whether a migration is needed.
- **Dec:** whether an owner decision is needed.

### 3.1 Security, identity and access (Phase A)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| SEC-01 | Server-side legal acceptance | FBV | IMPLEMENTED_NOT_VERIFIED (#353, not in `main`) | Only `/auth/me` reports it (`auth/saas.py:172`); no route checks it | A middleware gate with an allowlist for auth, acceptance, export, deletion and support | P0 | No | No |
| SEC-02 | Owner identity only from the server role | O | COMPLETED_AND_VERIFIED | `auth/owner_role.py:89-106`; `tests/test_no_runtime_ddl.py:267-279` | — | — | — | — |
| SEC-03 | Plan gate on the server | FBV | COMPLETED_AND_VERIFIED | `require_feature` (`auth/saas.py:344-374`); route-gate inventory test | — | — | — | — |
| SEC-04 | A paid subscription needs a known end | BV | COMPLETED_AND_VERIFIED | #351, `tests/test_subscription_end_required_pg.py` | PRE-MERGE read-only counts (in #351) | — | — | — |
| SEC-05 | Background mail uses the same entitlement as the interactive routes | V | COMPLETED_AND_VERIFIED | #351 | — | — | — | — |
| SEC-06 | Tenancy (account + workspace) | FBVO | COMPLETED_AND_VERIFIED for the Users interactive paths (audit 2026-10-09: no HIGH); defense in depth for mail candidates in #355 | Users services filter by workspace; OAuth bound to the session (`user_product/mail_oauth.py:336-356`) | A systematic review of every Users query | P0 | No | No |
| SEC-07 | Read purity (GETs don't write) | FBV | COMPLETED_AND_VERIFIED for Users | `tests/test_get_routes_are_read_only.py`. Exceptions are Owner-only (P0.2b currency alerts UPDATE, P5.2c snapshots, P0.2c radar) | Owner exceptions are tracked as Owner P0 | P0 (O) | No | O |
| SEC-08 | Idempotency of financial writes | FBV | COMPLETED_AND_VERIFIED | `core/idempotency.py` (movements, debts, payments, goals, savings, budget, recurring); `core/test_idempotency_atomicity.py`; both apps send `X-Idempotency-Key` | — | — | — | — |
| SEC-09 | Repeated confirmation of a mail candidate | V | COMPLETED_AND_VERIFIED | `FOR UPDATE` plus `already_reviewed` (`user_product/gmail_service.py:508-531`) | — | — | — | — |
| SEC-10 | Legal acceptance IP | FBV | PARTIALLY_IMPLEMENTED | `auth/legal.py:35` takes the first `X-Forwarded-For` value, which the client controls | Use the proxy-appended address (needs the Render proxy chain confirmed) | P1 | No | No |
| SEC-11 | Owner bridge (12-hour session from an API key) | O | IMPLEMENTED_NOT_VERIFIED | `auth/owner_bridge.py:71-91`; checks `allowed_users`, not `accounts.role` | Documented risk; not changed (Owner) | P1 (O) | No | O |
| SEC-12 | Rate limiting / abuse controls | FBV | IMPLEMENTED_NOT_VERIFIED (#361) | `docs/operations/observability.md:159` | A per-account limit on write routes (V1-14) | P1 | No | No |
| SEC-13 | Single-owner roles in the database | O | BLOCKED_BY_MIGRATION | PR #319 | Kenneth's authorization after #318 is verified in production | P0 | Yes | Yes |
| SEC-14 | Web lab restricted to the Owner (K-6) | — | BLOCKED_BY_DECISION | `frontend/README.md`; K-6 | A production config change | P1 | No | Yes |

### 3.2 Movements and mail (V1-4, V1-5)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| MOV-01 | Manual entry, edit and delete | FBV | COMPLETED_AND_VERIFIED | `user_product/free_service.py`; iOS `MovementsView.swift`, Android `MovementsScreen.kt` | — | — | — | — |
| MOV-02 | Type filter faithful to the movement type | FBV | PARTIALLY_IMPLEMENTED (depends on P0.3a canonical ledger types; not started) | Android classifies debts with a regex (`MovementsScreen.kt:82`); iOS has no Deudas filter | P0.3a/b/c ledger types | P1 | Maybe | No |
| MOV-03 | Category, account and period filters | FBV | NOT_IMPLEMENTED (pending decision: only mail-imported movements carry an account; how manual ones answer an account filter is undocumented) | Proposal D04 → P5.1 | A backend analysis endpoint | P1 | No | No |
| MOV-04 | Mail detection (Gmail/Outlook) with confirmation | V | COMPLETED_AND_VERIFIED (code) | `user_product/gmail_service.py`, `microsoft_mail.py`; candidates stay pending until reviewed | Gmail restricted-scope verification + annual CASA (`docs/security/google-oauth-verification.md:240`) | P0 | No | **Yes** (CASA, which plan) |
| MOV-05 | Validated Costa Rican bank formats | V | PARTIALLY_IMPLEMENTED | Onboarding offers 8 institutions; the parser reads 3 (proposal B3) | Parsers per validated bank, with synthetic fixtures | P0 | No | Yes (bank list) |
| MOV-06 | Mail duplicate prevention | V | COMPLETED_AND_VERIFIED | `email_monitor/deduplication.py`, `user_product/candidate_resolution.py` | — | — | — | — |
| MOV-07 | Owner automatic mail commit | O | Owner-exclusive (kept) | `email_monitor/service.py:1615-1640` | Not changed (V1-5a) | — | — | — |

### 3.3 Accounts and balances (V1-7)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| ACC-01 | Accounts detected from mail (no balance) | V | COMPLETED_AND_VERIFIED | `FinancialIdentity`; iOS `AccountsViews.swift`, Android `AccountsScreens.kt` | — | — | — | — |
| ACC-02 | Declared opening balance | FBV | NOT_IMPLEMENTED | Proposal I05 → P2.8a/b/c | Schema and endpoints | P0 | **Yes** | Yes (reconciliation policy) |
| ACC-03 | Estimated balance from confirmed movements | FBV | NOT_IMPLEMENTED | — | Engine on top of ACC-02 | P0 | Yes | Yes |
| ACC-04 | Reconciliation, estimated vs verified | FBV | NOT_IMPLEMENTED | — | Policy and engine | P0 | Yes | Yes |
| ACC-05 | Net worth | FBV | BLOCKED_BY_DECISION | K-3 / P0.9; VIP net worth treats unknown assets as 0 (`user_product/vip_service.py:186-206`, not shown publicly) | P0.9 after ACC-02..04 | P0 | Yes | Yes |

### 3.4 Debts (V1-10)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| DEB-01 | Create, list and delete | FBV | COMPLETED_AND_VERIFIED | `user_product/service.py`; native debts screens | — | — | — | — |
| DEB-02 | Edit | BV (Free can't) | PARTIALLY_IMPLEMENTED | `PUT` requires `strategy_basic` (`user_product/routes.py:103`); proposal P-1 / P2.1 says representing your own reality is never charged | Free edit | P0 | No | **Yes** (confirm P2.1) |
| DEB-03 | Unknown monthly payment ≠ 0 | FBV | BLOCKED_BY_MIGRATION (code + migration in #354; migration not run) | `float(payload.monthly_payment or 0)` (`user_product/service.py:274,370`); column `NOT NULL` (`database/schema.sql:70`) | Nullable column + provenance (as #329 did for the interest rate) + code. The migration is prepared, never run | P0 | **Yes** | No |
| DEB-04 | Interest rate known/unknown | FBV | COMPLETED_AND_VERIFIED | #328/#329 | — | — | — | — |
| DEB-05 | Payment (partial) | FBV | COMPLETED_AND_VERIFIED | `POST /finance/debts/{id}/payments`, idempotent, capped at the balance | — | — | — | — |
| DEB-06 | Extra payment as its own type | FBV | NOT_IMPLEMENTED | — | Payment type or tag | P1 | Maybe | No |
| DEB-07 | Payment history and reversal | FBV | NOT_IMPLEMENTED | Proposal G12 → P2.2a/b, P2.6 | Ledger of payments | P0 | Yes | No |
| DEB-08 | Due vs paid (installments never assumed paid) | FBV | COMPLETED_AND_VERIFIED (reads) | #307: reads never apply installments; `apply_due_installments` is an explicit command | K-4 redesign for automation | P1 | Maybe | Yes (K-4) |
| DEB-09 | Payoff plan / calendar | BV | PARTIALLY_IMPLEMENTED (waits for #354: the strategy engine reads an unknown payment/balance as 0) | Endpoint exists with no client (proposal G13) | Client screens | P1 | No | No |

### 3.5 Planning (V1-11)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| PLN-01 | Budgets by category | BV | COMPLETED_AND_VERIFIED | `basic_service.py`; Plan → Tu plan del mes → Presupuesto | Canonical categories (P0.10/P2.9); proposed limits from unknown income are 0 (`basic_service.py:70-73`) | P1 | No | No |
| PLN-02 | Recurring / fixed items | FBV | COMPLETED_AND_VERIFIED | UX-9 (#332); Plan → Ingresos y base → Movimientos recurrentes | Full edit (P2.4) | P1 | No | No |
| PLN-03 | Financial calendar | BV | COMPLETED_AND_VERIFIED | `/basic/calendar`; Plan → Tu plan del mes | — | — | — | — |
| PLN-04 | Savings goals | FBV | PARTIALLY_IMPLEMENTED (iOS savings-plan edit in progress: `v1/pln-04-ios-savings-edit`; Free edit waits for BLK-P21) | Free can't edit (`routes.py:123`, P2.1); iOS savings-plan edit missing (P2.5) | Free edit (needs the P2.1 decision), iOS edit | P1 | No | Yes (P2.1) |
| PLN-05 | Emergency fund (Salvavidas) | V | PARTIALLY_IMPLEMENTED | VIP only, read-only on both apps; G18 → P3.4 for Free/Basic | Plan mapping | P1 | No | Yes |
| PLN-06 | Budget alerts | V | PARTIALLY_IMPLEMENTED | Para atender is VIP; Free/Basic are hidden (`home.attention` transitional) | Decision on Free/Basic alerts | P1 | No | Yes |
| PLN-07 | Monthly summary and comparison | FBV | COMPLETED_AND_VERIFIED | Resumen (#349), Reportes (B+) | iOS/Android text parity (Resumen, Reportes) | P1 | No | No |
| PLN-08 | Basic strategy with unknown essentials | B | PARTIALLY_IMPLEMENTED | Unknown essentials become 0 and only warn (`user_product/strategy_engine.py:113-143`) | Present "incomplete" instead of a margin. This is an engine contract change | P0 | No | Yes (engine output) |

### 3.6 Analysis, projections, health (V1-8, V1-9)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| ANA-01 | Summary charts E04/E05 | FBV | COMPLETED_AND_VERIFIED | #349 | 6/12-month series (needs a backend parameter) | P1 | No | No |
| ANA-02 | Projections (one scenario, 1/3/6/12 months) | V | COMPLETED_AND_VERIFIED | #336, #347 | — | — | — | — |
| ANA-03 | Base / favorable / unfavorable scenarios | V | BLOCKED_BY_DECISION | V1-9 | Approved assumptions | P0 | No | **Yes** |
| ANA-04 | What-if simulations | V | COMPLETED_AND_VERIFIED | Escenarios (`/strategy-vip/simulate`) | — | — | — | — |
| ANA-05 | Health score 0–100 | FBV | BLOCKED_BY_DECISION | K-2, V1-8; non-canonical scores hidden (#337) | Formula, weights, thresholds. Architecture can be built without them | P0 | No | **Yes** |

### 3.7 Notifications (V1-12)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| NOT-01 | In-app notifications (Para atender) | V | COMPLETED_AND_VERIFIED | UX-5 (#325) | Free/Basic (PLN-06) | P1 | No | Yes |
| NOT-02 | Native push (APNs/FCM) | FBV | BLOCKED_BY_EXTERNAL_SERVICE | `notifications/routes.py` is Owner-only web push (VAPID); no APNs/FCM in either app | Provider accounts and keys, consent screen, preference storage, dedupe | P0 | Yes | Yes (events and defaults) |
| NOT-03 | Notification preferences | FBV | NOT_IMPLEMENTED | — | Schema and screens | P0 | Yes | Yes |

### 3.8 Subscriptions and billing (V1-2, V1-17, V1-18)

| ID | Function | Plans | State | Evidence | Missing | Pri | Mig | Dec |
|---|---|---|---|---|---|---|---|---|
| BIL-01 | Store verification on the server | BV | IMPLEMENTED_NOT_VERIFIED | `product_ops/store_verification.py`, `store_apple.py`, `store_google.py`; switch `DINCR_STORE_VERIFICATION_ENABLED` off | Sandbox purchases with test accounts | P0 | No | No |
| BIL-02 | Google Play Billing in the app | BV | IMPLEMENTED_NOT_VERIFIED | Android `StoreBilling`; flag `store_billing` off | Play-signed build, license testers | P0 | No | No |
| BIL-03 | StoreKit in the app | BV | NOT_IMPLEMENTED | iOS shows "Las suscripciones desde el App Store llegan en una próxima versión" (`ProfileViews.swift:249`) | StoreKit 2 purchase/restore, server verification | P0 | No | No |
| BIL-04 | VIP price ₡5.990 | V | BLOCKED_BY_DECISION | ₡4.990 in `product_ops/service.py:27`, `product_ops/store_billing.py:20`, `frontend/landing/config.json:9`, **the terms** (`frontend/landing/legal-en.mjs:19`, `frontend/src/pages/PublicInfoPage.jsx:47`), native fixtures | A new terms version (legal change) together with the price | P0 | Maybe | **Yes** |
| BIL-05 | Annual plans | BV | BLOCKED_BY_DECISION | `store_billing.py:21` placeholder `FINVA_VIP_ANNUAL_CRC` 49900 (not approved) | Annual prices and discount | P0 | No | **Yes** |
| BIL-06 | Launch promotion (VIP free until 2027-01-01) | BV | BLOCKED_BY_DECISION | `product_ops/service.py:23-24,424-457` | Keep, end or adjust for a commercial launch | P0 | No | **Yes** |

### 3.9 Native apps and release (Phases C, D)

| ID | Function | State | Evidence | Missing | Pri |
|---|---|---|---|---|---|
| NAT-01 | Five-tab navigation and plan locks, iOS = Android | COMPLETED_AND_VERIFIED | `native/feature-reachability.json` walkers on both platforms | — | — |
| NAT-02 | Android resume: a transient failure moves the app to the identity-error screen | IMPLEMENTED_NOT_VERIFIED (#360) | Android `AppModel.kt` `onForeground` → `loadIdentity()`; iOS keeps the user | Use the transient rule on resume (B17 finding) | P1 |
| NAT-03 | A failed refresh keeps content on Hoy and Movimientos | IMPLEMENTED_NOT_VERIFIED (#360) | iOS `HomeView.swift:61-62`, Android `MovementsScreen.kt:106`, both platforms | Keep content (B17 finding) | P1 |
| NAT-04 | Release signing on both platforms | NOT_IMPLEMENTED | No `signingConfigs`; iOS has no team (`native/RELEASE_IDENTITY.md:105-111`) | Human setup | P0 |
| NAT-05 | Crash reporting | NOT_IMPLEMENTED | None on either app | Provider decision (cost, privacy) | P0 |
| NAT-06 | Physical device pass | NOT_IMPLEMENTED | — | Human | P0 |
| NAT-07 | Store screenshots after UX-13 | NOT_IMPLEMENTED | `store-assets/` predates the five tabs | Regenerate | P1 |

## 3.10 Findings recorded during execution (not yet changed)

| Finding | Where | Next |
|---|---|---|
| The public store entitlement treats a missing end as active | `product_ops/store_billing.py` `_public_state` (`entitlement_end is None or …`) | Small backend PR (same rule as #351) |
| Android treated `grace` (not the backend's `grace_period`) as live, so a subscription in grace could start a second purchase | `core/data/.../OpsModels.kt` | Fixed in the BIL-03 PR |
| The data export includes the Owner's internal notes on the user's own support tickets | `auth/data_export.py` (`feedback_reports.owner_notes`) | Decision: export them or not |
| `uq_accounts_primary_email_ci` exists only in `database/schema.sql`, not in `migrations/` | the legacy `users` mapping by email relies on it | Read-only production check |
| VIP command center timeline adds an unknown debt payment as 0 to its projected balance | `user_product/vip_service.py` timeline | Formula decision (residual of DEB-03) |
| `calculate_debt_strategies` turns an unknown monthly payment or balance into 0 (`_as_float`) | `finance/strategic_engine.py` | A client for `/vip/debt-strategies` (DEB-09) waits for #354 (DEB-03) and its engine follow-up |
| A movement has no canonical type (debt payment, transfer…); Android's Deudas filter is a regex | `user_product/free_service.py` `list_free_movements` | MOV-02 waits for P0.3a (canonical ledger types) |
| Android Hoy was not refreshed by a swipe from the screen root in tests (the B17 test counted the start-up reload) | `PullToRefreshUiTest` | Fixed in the NAT-02/03 PR (swipe on the refresh box) |

## 4. Blockers that need Kenneth

| ID | What is needed | Blocks |
|---|---|---|
| BLK-PRICE | Approve a new terms version with VIP ₡5.990 (the terms text quotes ₡4.990) | BIL-04 |
| BLK-ANNUAL | Annual prices and discount. Note: the backend catalog already names annual product ids and a placeholder price (`FINVA_*_ANNUAL_CRC`); do not create annual store products until approved | BIL-05 |
| BLK-TRIAL | A 7-day free trial is declared in the store catalog (`FINVA_STORE_TRIAL_DAYS`, default 7) and is not approved; trials are set on the store products | BIL-01..03 |
| BLK-PROMO | Launch promotion: keep, end or adjust | BIL-06 |
| BLK-MAIL | Gmail restricted-scope verification and the annual CASA assessment; which plan gets mail detection; the list of validated banks | MOV-04, MOV-05 |
| BLK-HEALTH | Health formula, weights and thresholds | ANA-05 |
| BLK-SCEN | Assumptions for the favorable and unfavorable scenarios | ANA-03 |
| BLK-P21 | Confirm P2.1: Free edits its own debts and goals (P-1 says representing your own reality is never charged; the code requires Basic) | DEB-02, PLN-04 |
| BLK-ENGINE | The Basic strategy shows "incomplete" instead of a margin built from unknown essentials | PLN-08 |
| BLK-BAL | Reconciliation policy for declared vs estimated vs verified balances | ACC-02..05 |
| BLK-PUSH | Push provider accounts (APNs/FCM), events and defaults | NOT-02, NOT-03 |
| BLK-MIG | Authorize migrations (DEB-03 when its PR is ready; #319) | DEB-03, SEC-13 |
| BLK-REL | Signing, store accounts, crash reporting provider, physical pass | NAT-04..06 |

## 5. Execution order (only blocks that are not blocked)

1. **SEC-01:** server-side legal acceptance (no migration, no decision).
2. **DEB-03:** unknown monthly payment. Migration and code are prepared in one PR, with a PRE-MERGE GATE; the migration is never run.
3. **NAT-02 / NAT-03:** Android resume, and refresh that keeps content (B17 findings).
4. **SEC-06:** systematic tenancy review of the Users queries.
5. **SEC-10:** legal acceptance IP (once the proxy chain is confirmed).

## 6. Work log

| Block | Branch | PR | State | Tests |
|---|---|---|---|---|
| Master record | `v1/master-execution-doc` | #352 | open | docs only |
| SEC-01 server-side legal acceptance | `v1/sec-01-legal-gate` | #353 | open, ready for review | backend 2,743 (+7 PG gate tests; 5 fail on `main`) |
| DEB-03 unknown monthly payment | `v1/deb-03-unknown-monthly-payment` | #354 | open; **PRE-MERGE GATE: migration 20261010120000 applied first + label** | backend 2,748 (+12 PG tests; 7 fail on `main`); iOS kit 322, Android core 306 |
| SEC-06 candidate scope (defense in depth) | `v1/sec-06-candidate-scope` | #355 | open, ready for review | backend 2,739 (+3 PG tests; the real review path on `main` loads another workspace's candidate) |
| Store public state needs a known end (follow-up of #351) | `v1/bil-public-state-end` | #356 | open, ready for review | backend 2,737 (+1; fails on `main`) |
| V1-1 recorded (CLAUDE.md, native RELEASE_IDENTITY/README) | `v1/docs-native-is-official` | #357 | open, ready for review | engineering guards 5/5 |
| PLN-01 guided budget never proposes from an unknown income | `v1/pln-budget-unknown-income` | #358 | open, ready for review | +7 tests (4 fail on `main`; the 3 known cases pass on both) |
| PLN-07 monthly summary: unknown savings / no goals | `v1/summary-unknown-savings` | #359 | open, ready for review | backend 2,741 (+5; 3 fail on `main`) |
| NAT-02/03 keep content on failed refresh, Android resume | `v1/nat-02-03-keep-content` | #360 | open, ready for review | iOS DincrKit 322, UI 119 (1 known flake, passes on rerun); Android unit 306, UI 116, 320×640 14; mutations caught on both |
| BIL-03 StoreKit (iOS) | `v1/bil-03-storekit` | (in progress) | code + unit + UI tests; full iOS suite pending | DincrKit StoreModels 5/5; UI 3/3; Android unit 307 (`StoreEntitlementTest` fails on `main`) |
| SEC-12 per-account write cap (429 + Retry-After) | `v1/sec-12-write-rate-limit` | #361 | open, ready for review | backend 2,746 (+10; 4 app-level fail on `main`) |
| DEB-07a debt payment history (read-only) | `v1/deb-07a-payment-history` | (in progress) | backend + iOS + Android done; full suites running | backend 2,740 (4 new fail on `main`); Android UI 1/1, mutation caught |

## 7. How to resume

1. **Refresh and check:** `git fetch origin '+refs/heads/*:refs/remotes/origin/*'`, then `gh pr list --state open`. Compare with §6.
2. **Read in order:** this file (from its PR branch while it is unmerged), then each PR in §6 that is still open.
3. **Choose the next block:** the next one in §5 whose dependencies are in `main`. Each block gets a new branch from `origin/main`, with no stacking.
4. **Test commands:**
   - Backend: from `jarvis-personal/`, `DINCR_REQUIRE_PG_TESTS=1 python -m pytest -q backend` and `python -m pytest -q labs`, plus `python backend/scripts/check_file_size_budget.py` and `check_public_secrets.py`.
   - iOS: `swift test` in `native/ios/DincrKit`; `xcodebuild build-for-testing` / `test-without-building` on an iPhone simulator.
   - Android: `./gradlew :core:data:test :core:design:test` and `:app:connectedNativedevDebugAndroidTest` (API 36 emulator; 320×640 with `adb shell wm size 320x640; wm density 160`).
5. **Never:** merge, deploy, run migrations, change production config, activate payments, push or cron, or change Owner behavior.
