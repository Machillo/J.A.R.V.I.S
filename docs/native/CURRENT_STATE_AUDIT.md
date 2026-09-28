# DINCR native migration — current-state audit (Capacitor reference)

Status: **v1 — frozen reference of the public (Users) Capacitor app**, audited from source.
Scope: the commercial DINCR app (`src/App.jsx` → `src/users`, `src/products/finva`, the shared
`src/pages` screens it renders). The Owner app (`src/personal`, `src/products/jarvis`) is **out of
scope** for the native migration: it stays behind the Owner boundary and is not re-implemented natively.

Companion documents:
- [`PARITY_MATRIX.md`](PARITY_MATRIX.md) — feature-by-feature parity tracker (Capacitor → iOS → Android).
- This file — architecture, cross-cutting behavior, client-side logic classification, OpenAPI evaluation,
  and findings handed to other owners.

---

## 1. Boot and gating sequence (`src/App.jsx`)

The native apps must reproduce this exact gate order. Every gate is driven by `GET /auth/me`
unless noted.

| # | Gate | Condition | Screen | Notes |
|---|------|-----------|--------|-------|
| 0 | Release policy | `GET /product-ops/release-policy?platform&version` (unauthenticated, 8 s timeout, **fail-open**) | `ReleaseUpdateNotice` (blocking when `required`, dismissible banner when `optional`, dismissal stored per platform+version) | Re-checked on every app resume |
| 1 | Session boot | Supabase session not yet read | Boot screen "Inicializando sesión…" | |
| 2 | Signed out | no Supabase session | `Login` | Google on both platforms; **Sign in with Apple on iOS only** (guideline 4.8) |
| 3 | Identity error | `/auth/me` fails | Error screen: retry, open support, log out; **"Terminar eliminación"** when error code is `account_deletion_pending` (calls `DELETE /auth/me` then local sign-out) | |
| 4 | Loading identity | `/auth/me` pending | Boot screen | |
| 5 | Owner/admin role | `role ∈ {owner, admin}` | Owner app — **out of scope, never shipped in native Users apps** | Native apps must fail safe: an Owner session shows a "use the Owner app" notice, never Owner features |
| 6 | Legal consent | `legal.required` | `LegalConsent` (two checkboxes, both required; `POST` accept with `terms_version`/`privacy_version`) | Log out available |
| 7 | Profile setup | `!profile_setup_completed` | `ProfileSetup` 4 steps: name → goal → currency & number format → institutions | Saved once at the end (`POST /auth/profile-setup`) |
| 8 | Plan selection | `!plan_selected` | `FinvaWelcomeStory` (5 slides, skippable, shown once per account, local flag) → `FinvaOnboarding` plan cards | `GET /auth/plans`, `GET /product-ops/billing/catalog`; paid plans only selectable while `promotion.active`; plan confirmed via `confirmedPlanProfile` (response profile or fresh `/auth/me`) |
| 9 | App lock | biometric lock enabled for this user | `FinvaAppLock` (+ one-time `FinvaAppLockOnboarding`) | Local, per-user config; 5-minute inactivity timeout |
| 10 | App | — | `UsersApp` | |

On resume (`appStateChange` active): flush offline queue, refresh `/auth/me` (throttled 15 s, only
re-renders when identity/plan fields change), re-check release policy, re-evaluate app lock.

## 2. App shell (`src/users/UsersApp.jsx`)

- **Navigation**: 5 tabs — **Hoy** (`overview`), **Movimientos** (`finance`), **Plan** (`plan` hub),
  **DINCR** (`advisor` hub), **Perfil** (`profile` hub). Each tab owns a set of secondary routes that
  keep it highlighted (see `FinvaNavigation.jsx`). The DINCR tab shows a `!` badge for VIP when
  `vip_intelligence` is disabled.
- **History/back**: in-app stack on top of `history.pushState`; Android hardware back pops the stack
  and minimizes at root; iOS edge-swipe (28 px edge, 84 px distance) pops. Screens can intercept back
  (`finva:native-back`) — used by detail views and sheets.
- **Header**: product name, plan subtitle, per-plan title map (e.g. "Hola, {first name}"), avatar →
  Settings. VIP screens render their own header.
- **Global banners** (stacked, top of content, `role=status|alert`):
  1. optional-update banner;
  2. `financial_writes` disabled → "Cambios temporalmente pausados" with the server message;
  3. subscription `access_notice` (dismissible);
  4. health mode: offline / recovering / degraded / major outage, with "Ver estado" → Support;
  5. offline-queue pending count ("Cambio protegido");
  6. queue recovered / rejected notice;
  7. API failure help with "Abrir chat" (support) and the incident reference once reported.
- **Progressive profile nudge** (`ProgressiveProfileNudge`): contextual card asking for the next
  missing profile datum (observed income, essential expenses, debt interest, VIP goal priority);
  "Recordar después" dismissal is local.
- **Error boundary** per screen with retry and "Ir a soporte".
- **Feature flags** (`GET /product-ops/feature-flags`, cached, refreshed every 60 s / on resume /
  online): `financial_writes`, `gmail_automation`, `vip_intelligence`, `advanced_reports`,
  `store_billing`. Safe defaults: writes and mail **off** until the server says otherwise.
- **Platform health** `GET /product-ops/health`.
- **Product analytics**: screen-open events via `POST /product-ops/events` + telemetry screen names.

## 3. Routes by plan (`products/finva/features/registry.jsx`)

Plan is `user.subscription.plan` (`free` | `basic` | `vip`). "Gated" = replaced by `FeatureUnavailable`
when the flag is off.

| Route | Free | Basic | VIP | Gate |
|-------|------|-------|-----|------|
| overview | FinvaOverview (free) | Basic dashboard | VipScreens `dashboard` (falls back to FinvaOverview if `vip_intelligence` off) | — |
| finance | Movements list (compact) | same | same + VIP title | — |
| transactions | Full history + edit/delete | same | same | — |
| monthly | Monthly summary | same | same | — |
| plan / advisor / profile | Hubs (content differs by plan) | | | — |
| debts | Debts (simple) | Debts (advanced fields) | Debts (advanced) | — |
| goals | Goals + savings plans | same | VipScreens `goal` | — |
| savings | Goals, savings tab | same | same | — |
| budget, calendar, recurring | (reachable only via hub for Basic+) | ✓ | ✓ | — |
| reports | — | ✓ | ✓ | `advanced_reports` |
| strategy | StrategyBasic | StrategyBasic | VipStrategy (PremiumStrategy + optional actions) | VIP: `vip_intelligence`; always followed by `FinancialDisclaimer` |
| situation | FinancialSituation (plan-scoped fields) | | | — |
| settings | FreeSettings | Settings | Settings | — |
| plan-settings | Settings | Settings | Settings | — |
| more | FreeMore | BasicMore | VipScreens `more` | — |
| feedback | Support | Support | Support | — |
| gmail, accounts | Settings (fallback) | Settings (fallback) | GmailAutomation (mail / accounts views) | `gmail_automation` |
| vip-today, vip-reality, vip-emergency, vip-preferences | — | — | VipScreens | `vip_intelligence` |
| vip-recommendation, vip-projections, vip-projection-detail, vip-scenarios, vip-monthly-review | — | — | VipScreens + disclaimer | `vip_intelligence` |
| vip-aguinaldo | Settings (fallback) | Settings (fallback) | VipScreens `aguinaldo` + disclaimer | `gmail_automation` |

Non-VIP users that reach a VIP route see Settings (plan change), never the VIP feature.

## 4. Cross-cutting behavior the native apps must reproduce

| Concern | Capacitor implementation | Native requirement |
|---------|--------------------------|--------------------|
| Auth | Supabase OAuth PKCE in system browser (`Browser.open`), redirect `{appId}://auth/callback`, **only the `code` is accepted** (never tokens in the URL) | ASWebAuthenticationSession / Custom Tabs with PKCE; same callback rule; Supabase session refresh |
| Session storage | Supabase JS (WebView storage) | Keychain (iOS) / Keystore-backed encrypted storage (Android) |
| API auth | `authenticatedFetch` adds the Supabase access token | Same bearer token; refresh on 401 once, then sign out |
| API errors | `apiErrors.js` maps status/payload → localized message, auto-reports incidents (`POST /product-ops/incidents`, queued offline) | Shared error mapping per platform; same incident contract |
| Offline writes | `operationRecovery.js`: POST/PUT/PATCH to an allow-list of financial paths are queued per user (max 20, 32 KB, 24 h), sent with an idempotency operation id, flushed on online/resume/next success | Must be reproduced **with the same idempotency key contract** or explicitly dropped (then writes are blocked offline) — decision recorded in parity matrix |
| Double submit | `useSingleFlight` on create/save handlers | Disable action while in flight |
| Mail OAuth return | Deep link return with one-time completion code, redeemed by the same session (`POST /vip/mail/oauth/complete`), de-duplicated by `ret`, retried on network failure | Same flow; handled-return ledger persisted |
| App lock | Biometric or device credential, per-user local config, 5-min background timeout, "Bloquear ahora" | LocalAuthentication / BiometricPrompt (`BIOMETRIC_WEAK or DEVICE_CREDENTIAL`) |
| Theme | dark / light / system, stored locally; system follows the OS live | Native appearance setting with same three options |
| Language | `deviceLanguage()` → `es` or `en`; all copy is bilingual inline `tx(es, en)` | String catalogs (iOS `.xcstrings`, Android `strings.xml`) es + en |
| Money format | **Hard-coded CRC** narrow symbol, 0 decimals, device locale | Must not repeat the CRC hard-code; follow the currency contract being defined by Agent B (see §7) |
| Legal links | `LegalLink` → dincr.com terms/privacy | Same URLs, in-app browser |
| Support | Guided chat collecting problem/improvement, `POST /product-ops/feedback`, status + resolution feedback | Same |
| Data export | `GET /auth/me/export` → JSON saved/shared via Filesystem + Share | Share sheet / SAF |
| Account deletion | Confirmation dialog → `DELETE /auth/me` → local sign-out; resumable "finish deletion" | Same, with destructive confirmation |
| Analytics | PostHog product analytics + `/product-ops/events`; contract in `analyticsContract.js` | Same event names; no PII (CLAUDE.md §4.F) |
| Push | Web-push helper exists but is only wired from the Owner/legacy `src/pages/Settings.jsx`; **Users app has no push notifications today** | Not required for parity |

## 5. Client-side logic classification

Native clients must not re-implement financial logic (goal contract §6). Everything the Capacitor
client computes today, classified:

| Location | Computation | Class | Native decision |
|----------|-------------|-------|-----------------|
| `users/pages/Debts.jsx` `monthsLeft` | Amortization: months to pay off from balance, payment, annual rate (log formula) | **Business logic** | **Backend consolidation dependency** — expose `months_remaining` per debt from `/finance/debts`. Native shows backend value only; until then show "—" rather than duplicating the formula |
| `movementPreview.js` | Classifies a movement as `debt` by regex on category/description (`deud|debt|préstamo|loan|cuota`) | **Business logic (classification)** | Backend dependency — `/free/movements` should return a `kind`. Native: filter on `transaction_type` + backend kind |
| `FinvaOverview.jsx` BasicDashboard | Budget spent sum, `used %`, `available = available_for_categories − spent` (floored at 0) | Business-adjacent (derived money figure) | Backend dependency — `/basic/budget` should return `total_spent`, `used_percent`, `available`. Short term native may mirror *display-only* sums, documented |
| `Budget.jsx` / `VipScreens` reality | Sum of limits/spent, per-category over/left | Presentation aggregation of returned rows | Acceptable in client (pure sums of returned rows), but prefer backend totals |
| `Debts.jsx`, `TransactionDebts.jsx`, `Goals.jsx`, `FreeScreens.jsx` | Totals and progress % from returned rows | Presentation aggregation | Acceptable (display-only), prefer backend totals |
| `Finance.jsx` (non-compact path) | Income/expense totals | Presentation | Dead path today (all plans use compact) |
| `FinancialSituation.jsx` | Profile completeness % | Presentation | Acceptable |
| `Reports.jsx` | Month shifting, N parallel report calls | Presentation | Acceptable; a range endpoint would be better |
| `PremiumStrategy.jsx` | `allocation_total` fallback sum | Presentation fallback | Use backend value only |

## 6. OpenAPI / typed-client evaluation

Findings (static audit of `backend/**/routes.py`):

- FastAPI app `Jarvis Core`; OpenAPI is generated by default.
- **Request bodies are typed** (Pydantic `…Request` models imported by the routers).
- **No route declares `response_model`** (0 of ~290 across all routers, including the 74 `/user-product`
  routes). OpenAPI response schemas are therefore empty (`{}`), so generated clients would return
  untyped JSON.
- Some request bodies are `dict` (e.g. the Gmail push webhook — not a client endpoint).

Decision:
1. **Generate request models** for Swift and Kotlin from the backend OpenAPI document with one
   pinned generator (`openapi-generator` via Docker or jar, config committed), output committed and
   regenerated by a script; CI drift check once a Python 3.11 environment is available locally.
2. **Response models** are hand-written, minimal, per-screen `Decodable` / `@Serializable` structs
   that decode *only the fields the screen displays*, with unknown keys ignored. Each is validated by
   a JSON fixture test captured from the Capacitor contract (field names used in JSX).
3. **Backend dependency (Agent A / API owner)**: add `response_model`s to `/auth/me`, `/auth/plans`,
   and the `/user-product/*` routes the native apps consume. When they land, response structs switch
   to generated models and the hand-written ones are deleted.

## 7. Findings handed to other owners (not fixed here)

| # | For | Finding | Evidence |
|---|-----|---------|----------|
| F1 | Agent A (Owner boundary, §4.A) | `src/pages/PremiumStrategy.jsx`, rendered for **Users VIP** via `users/pages/VipStrategy.jsx`, contains Owner-flavored hard-coded copy and categories: "Saldo disponible en MultiMoney", "Deudas, Casa y Línea entran solas", "Gym, Muay Thai, suscripciones…", "Saldo IBKR…", "salarios oficiales de la CCSS". Needs review whether shared VIP UI encodes Owner-specific configuration | `grep -n "MultiMoney\|Muay\|IBKR\|Casa" frontend/src/pages/PremiumStrategy.jsx` |
| F2 | Agent A (API contract) | No `response_model` on any route → OpenAPI cannot type responses (see §6) | `backend/*/routes.py` |
| F3 | Agent B (CRC/USD) | Every Users screen formats money with a hard-coded `currency: "CRC"` regardless of `base_currency` / `enabled_currencies` chosen in ProfileSetup | `grep -rn 'currency:"CRC"\|currency: "CRC"' frontend/src/users frontend/src/products/finva` |
| F4 | Agent A/B (read vs write, §4.C) | Opening the VIP dashboard fires `POST /user-product/vip/lifecycle/snapshots` from the client. Snapshot creation is not a financial-truth mutation, but it is a write triggered by a read surface; the native apps should not have to replicate it — backend could own snapshot cadence | `VipScreens.jsx:82` |
| F5 | Backend consolidation | Business logic in the client (§5): debt months-remaining formula, debt classification regex, Basic "available" figure | §5 |
| F6 | Cleanup (Agent B) | Unused Users API functions: `uploadPaymentReceipt`, `getStoreBillingCatalog`, `getStoreEntitlement`, `createTransaction`, `deleteTransaction`, `getFinanceSummary`; non-compact Finance path unreachable | `users/services/jarvisApi.js` |

## 8. Local toolchain (for later phases)

| Tool | State | Note |
|------|-------|------|
| Xcode | `/Applications/Xcode.app` installed; `xcode-select` points to CommandLineTools | Builds use `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` (no `sudo` needed) |
| Android SDK | `platforms/android-36`, `build-tools/35.0.0` | Gradle via wrapper |
| JDK | Temurin 17 and 21 | |
| Python for backend/OpenAPI | Only system 3.9 without deps; CI uses 3.11 | Needed to export `openapi.json` locally |
