# DINCR native parity matrix

Version: **v1** · Reference: Capacitor Users app on `main` (see [`CURRENT_STATE_AUDIT.md`](CURRENT_STATE_AUDIT.md)).
Scope: public DINCR (Free / Basic / VIP). The Owner app is out of scope.

## Status legend

| Status | Meaning |
|--------|---------|
| `—` | Not started |
| `WIP` | In progress |
| `PASS` | Implemented, all listed states covered, tests pass |
| `DIFF` | Intentional platform-specific difference (documented in Notes) |
| `HUMAN` | Implemented; needs physical-device / console validation (script in release doc) |
| `BLOCKED` | Blocked on a dependency (named in Notes) |
| `N/A` | Not required on this platform |
| `CI` | Implemented; compiled and tested only in CI (macOS runner, simulator). Never run on a device |

Tests column: **U** unit/contract tests (`core:data`, `DincrKit`) · **UI** Compose flows on an
emulator and/or XCUITest on a simulator, against the in-process fake backend.

States column abbreviations: **L** loading · **E** error · **∅** empty · **OK** success feedback ·
**X** destructive confirmation · **OF** offline behavior · **G** plan/flag gate · **V** validation.

Every feature row must reach `PASS`, `DIFF`, `HUMAN` or `N/A` on both platforms before the
migration is declared complete.

---

## A. Boot, identity and gating

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| A1 | Release policy gate | Blocking screen when `required`; dismissible banner when `optional` (per platform+version); re-check on resume; fail-open | `GET /product-ops/release-policy` | L, E(fail-open) | CI | PASS | U | Store URL per platform; Android: fail-open after 8 s; required → blocking screen, optional → dismissible banner; iOS: fail-open after 8 s; required → blocking screen with the store link |
| A2 | Login — Google | OAuth PKCE in system browser, callback accepts `code` only | Supabase Auth | L, E | HUMAN | HUMAN | U | PKCE S256 unit-tested; live Google sign-in needs a device; iOS: `com.dincr.app://auth/callback` in ASWebAuthenticationSession (ephemeral) |
| A3 | Login — Apple | iOS only | Supabase Auth (Apple) | L, E | HUMAN | N/A | U | Guideline 4.8; Android shows Google only; iOS: Supabase web OAuth like Capacitor (no native Sign in with Apple entitlement) |
| A4 | Session restore / sign-out | Session persists; sign-out is local scope; identity change resets user | Supabase Auth | — | PASS | PASS | U | Keychain / Keystore; Session epoch, refresh race and local-first logout (#279) kept |
| A5 | Identity load error | Retry, support, log out | `GET /auth/me` | E | PASS | PASS | UI | |
| A6 | Finish pending deletion | Shown when `/auth/me` returns `account_deletion_pending` | `DELETE /auth/me` | L, E, X | CI | PASS | U | |
| A7 | Owner session in Users app | Capacitor routes to Owner app | `/auth/me` role | G | DIFF | DIFF | U | **DIFF**: native Users apps never render Owner features; show "use the Owner app" + sign-out |
| A8 | Legal consent | Two required checkboxes, doc links, version shown, log out | `POST /auth/legal/accept` then `GET /auth/me` | L, E, V | CI | PASS | UI | Versions come from `/auth/me.legal`, never invented |
| A9 | Profile setup (4 steps) | Name → goal (6 options) → base + extra currencies, number format, symbol position, live preview → institutions (search, 8 banks, logos, "supported" badge) | `POST /auth/profile-setup` | L, E, V | PASS | PASS | UI | Saved only at the end; back button per step |
| A10 | Welcome story | 5 slides, skip, once per account (local flag) | — | — | — | — | — | Not ported (welcome story); low risk |
| A11 | Plan selection | Expandable plan cards, price from billing catalog, paid plans only while promotion active, retry for plans and billing | `GET /auth/plans`, `GET /product-ops/billing/catalog`, `POST /auth/plan` | L, E, G | CI | PASS | UI | Plan confirmed from response or fresh `/auth/me`; Paid plans only with the launch promotion; otherwise "coming to the stores" |
| A12 | App lock onboarding | One-time offer to enable biometrics after first login | local | — | CI | HUMAN | — | Android: enabling requires a successful biometric/credential prompt; iOS: one-time alert after sign-in |
| A13 | App lock | Biometric or device passcode; 5-min background timeout; unlock / log out; error mapping (cancel, not enrolled, lockout, no passcode) | local | E | HUMAN | HUMAN | U | HUMAN: Face ID / fingerprint; Android: BIOMETRIC_WEAK or DEVICE_CREDENTIAL, 5 min on elapsedRealtime; iOS: LocalAuthentication (.deviceOwnerAuthentication), 5 min on systemUptime; the lock replaces the shell |
| A14 | Profile refresh on resume | Throttled 15 s; only re-render on identity/plan change | `GET /auth/me` | — | CI | PASS | — | Android: 15 s throttle on resume |

## B. Shell and cross-cutting

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| B1 | Tab bar (5 tabs) + active-route mapping | Hoy, Movimientos, Plan, DINCR, Perfil; VIP badge when intelligence off | — | G | CI | PASS | UI | iOS TabView; Android NavigationBar; Android: bar < 600 dp, rail ≥ 600 dp. iOS: DINCR tab still a placeholder |
| B2 | Back navigation | In-app stack; Android back pops then minimizes; iOS edge swipe | — | — | PASS | PASS | UI | Native nav stacks |
| B3 | Header | Plan subtitle, per-plan titles, avatar → settings | `/auth/me` | — | — | WIP | — | Plan badge in Profile; no per-plan header subtitle |
| B4 | Feature flags | 5 flags, safe defaults, 60 s refresh, cache | `GET /product-ops/feature-flags` | G | CI | PASS | U | 60 s refresh on Android; iOS loads on entry; iOS: loaded on entry and on resume |
| B5 | Writes-paused banner | When `financial_writes` off | flags | G | CI | PASS | U | Also disable write actions; iOS: banner and hidden actions on the Plan tab only |
| B6 | Subscription access notice | Dismissible banner from `subscription.access_notice` | `/auth/me` | — | CI | PASS | — | |
| B7 | Health mode banner | offline / recovering / degraded / outage + "Ver estado" | `GET /product-ops/health`, reachability | OF | WIP | WIP | — | NWPathMonitor / ConnectivityManager; Android: degraded/outage banners from `/product-ops/health`; no reachability monitor; iOS: health banners; no reachability monitor |
| B8 | Offline write queue | Allow-listed POST/PUT/PATCH queued per user (20 ops, 32 KB, 24 h) with operation id; flush on reconnect/resume; recovered/failed notices | idempotent write endpoints | OF | DIFF | DIFF | U | Decision pending: reproduce with same idempotency contract vs. block writes offline; No offline queue: a write offline fails with a clear message; retrying the same submission reuses its idempotency key |
| B9 | API error help + incident report | Auto-report incident, show reference, open support | `POST /product-ops/incidents` | E | — | — | — | Not ported (incident auto-report) |
| B10 | Progressive profile nudge | Next missing datum card, dismiss locally | `GET /user-product/financial-situation` | — | — | PASS | — | |
| B11 | Screen error boundary | Retry + go to support | — | E | — | — | — | |
| B12 | Theme | dark / light / system (live) | local | — | PASS | PASS | — | |
| B13 | Language | es / en from device | — | — | PASS | PASS | — | String catalogs |
| B14 | Money formatting | Hard-coded CRC (finding F3) | — | — | PASS | PASS | U | BLOCKED on Agent B currency contract for multi-currency; native uses profile currency when defined; Profile base currency, separators and placement; entry currencies CRC/USD on Android |
| B15 | Product analytics | Screen events + telemetry | `POST /product-ops/events` | — | — | PASS | U | No PII; Android: allow-listed screen names only, no PII; iOS: no product events yet |
| B16 | Financial disclaimer | Shown under strategy / advisory screens | — | — | CI | PASS | — | |
| B17 | Feature unavailable | Replaces gated screens with server message | flags | G | CI | PASS | U | `503 feature_temporarily_unavailable` is a distinct error and is not retried |

## C. Overview (Hoy)

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| C1 | Free overview | Available this month, income/expenses, debt paid, KPIs, 6-month income vs expense bars, expenses by category, link to monthly summary | `GET /user-product/free/dashboard` | L, E, ∅ | PASS | PASS | UI | Charts: Swift Charts / Compose Canvas |
| C2 | Basic dashboard | Planned available, budget used %, quick links (budget, commitments, savings), next 7 days commitments, month plan progress | `GET /user-product/basic/dashboard`, `/basic/budget`, `/basic/calendar` | L, E, ∅ | CI | PASS | UI | "available"/"used %" computed client-side → backend dependency (audit §5); Android shows backend values only |
| C3 | VIP dashboard | Strategic available, top actions, recommended priority, 6-month projection summary, plan vs reality, monthly review, DINCR Today | `GET /user-product/vip/command-center`, `/financial-situation`, `/basic/budget`, `POST /vip/lifecycle/snapshots` | L, E(retry), G | DIFF | DIFF | UI | Snapshot POST on open (finding F4); Android never POSTs `/vip/lifecycle/snapshots` on open (reads do not write, §4.C); iOS: same as Android |

## D. Movements

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| D1 | Movements list | Search, filter tabs (all / income / expense / debt), sorted by date, read-only rows marked | `GET /user-product/free/movements` | L, E, ∅ | PASS | PASS | UI | "debt" kind is a client regex → backend dependency |
| D2 | Debts in Movimientos | Debt filter shows debt list (read-only) + "Gestionar" + debt payments | `GET /finance/debts` | L, E, ∅ | — | PASS | UI | iOS: no debt filter in Movements (debts live in Plan) |
| D3 | Add income / expense | Chooser sheet → form: amount, description, category (suggestions), date; single-flight | `POST /finance/income`, `POST /finance/expenses` | V, E, OF | CI | PASS | UI | Android: USD entry asks for the user's own rate (prefilled with their latest rate, never a market rate); iOS: CRC/USD with the user's own rate |
| D4 | Edit income / expense | Tap editable row → edit sheet | `PUT /finance/income/{id}`, `PUT /finance/expenses/{id}` | V, E, OF | CI | PASS | UI | Untouched currency fields keep original_amount/original_currency/exchange_rate |
| D5 | Full history | Search, type and category filters, edit and delete editable rows | `GET/PUT/DELETE /user-product/free/movements[/{id}]` | L, E, ∅, X | PASS | PASS | UI | iOS: rows with currency data stay read-only |
| D6 | Delete movement | Confirmation "no se puede deshacer" | `DELETE …` | X, E | PASS | PASS | UI | |
| D7 | Monthly summary | Month picker, KPIs (income, spent, balance, debt paid, savings, goals %), top category, distribution | `GET /user-product/free/monthly-summary?period` | L, E | CI | PASS | — | |

## E. Plan hub

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| E1 | Plan hub | Grouped links; Budget (Basic+), Calendar + Recurring (Basic+), Emergency + Aguinaldo (VIP) | — | G | CI | PASS | UI | iOS: debts and goals only |
| E2 | Debts list | Total, progress ring (Free), cards with payment/progress, next payment, months remaining | `GET /finance/debts` | L, E, ∅ | CI | PASS | UI | months remaining computed client-side (audit §5) → show backend value only |
| E3 | Debt create / edit | Name, balance, original, monthly payment; Basic+: type, annual interest, term, payment day, next date | `POST/PUT /finance/debts[/{id}]` | V, E, OF | CI | PASS | U | Edit needs Basic (backend `strategy_basic`) |
| E4 | Debt payment | Amount dialog | `POST /finance/debts/{id}/payments` | V, E, OF | CI | PASS | UI | Idempotency key per submission; amount bounded to NUMERIC(12,2) |
| E5 | Debt delete | Confirmation | `DELETE /finance/debts/{id}` | X | CI | PASS | — | |
| E6 | Goals | Total progress, list, detail, create/edit (name, target, saved, date, priority, status), contribute, delete; VIP smart goal card (recommended contribution from backend) | `/user-product/goals*`, `GET /vip/command-center` | L, E, ∅, V, X, OF | CI | PASS | UI | iOS: list and contribute only |
| E7 | Savings plans | Monthly amount, saved, start/end, status; contribute; delete | `/user-product/savings-plans*` | L, E, ∅, V, X, OF | CI | PASS | U | Free "more" shows savings summary |
| E8 | Budget | Month total spent / budgeted / available, per-category progress, over-limit state, edit limits mode | `GET/PUT /user-product/basic/budget` | L, E, V | CI | PASS | UI | |
| E9 | Financial calendar | Month picker, commitments count, known payments, events by day | `GET /user-product/basic/calendar?period` | L, E, ∅ | CI | PASS | — | |
| E10 | Recurring | Summary, list, pause/activate, delete, create (name, amount, category, type, frequency, due day) | `/user-product/basic/recurring*` | L, E, ∅, V, X, OF | CI | PASS | U | |
| E11 | VIP emergency fund (Salvavidas) | Coverage 1/3/6 months, saved balance, protected expenses | `GET/PUT /user-product/vip/salvavidas` | L, E, V, G | DIFF | DIFF | — | Shared PremiumStrategy copy under review (F1); Android: read-only from the financial situation; `PUT /vip/salvavidas` is Owner-shaped and not used; iOS: same as Android |
| E12 | VIP aguinaldo | Estimate from salaries | `GET /user-product/vip/aguinaldo` | L, E, G | CI | PASS | — | Gated by `gmail_automation`; 409 (not applicable) shown as an empty state |

## F. DINCR (advisor) hub

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| F1 | Advisor hub | Free → monthly summary; Basic → strategy; VIP → Today, direction, reality, monthly review, projections, scenarios | — | G | CI | PASS | — | |
| F2 | Strategy (Free/Basic) | Month guide, priority, estimated income, known installments, margin, recommended plan, next-income split, debt projection, smart goals, "what if I add more" simulation, director alerts, data gaps | `GET /finance/strategy-basic`, `POST …/simulate` | L, E | CI | PASS | — | Disclaimer below |
| F3 | VIP strategy | Optional actions + PremiumStrategy (sections: salvavidas, investment, debt advisory, allocation, aguinaldo) | `/finance/strategy-vip`, `/vip/strategy-dashboard`, `/vip/debt-advisory`, `/vip/salvavidas`, `/vip/aguinaldo` | L, E, G | DIFF | DIFF | — | F1 review first; Android uses `/finance/strategy-vip` only; `/vip/strategy-dashboard` and `/vip/debt-advisory` are Owner-shaped; iOS: same as Android |
| F4 | VIP recommendation | Recommended action, why, impact | command-center | G | CI | PASS | UI | |
| F5 | VIP projections + detail | 6-month evolution, per-debt projection | command-center | G | CI | PASS | — | Charts |
| F6 | VIP scenarios | Presets + custom (extra income, expense change, one-off money), comparison | `POST /finance/strategy-vip/simulate` | L, E, V, G | CI | PASS | — | Read-only simulation; Read-only simulation |
| F7 | VIP plan vs reality | Budget planned vs spent | budget, command-center | G | — | — | — | Not ported |
| F8 | VIP monthly review | Period picker, changes, next priority | `GET /vip/lifecycle/monthly-review` | L, E, G | CI | PASS | — | |
| F9 | VIP Today | Proactive advisor items | `GET /vip/lifecycle/proactive-advisor` | L, E, ∅, G | CI | PASS | — | |
| F10 | VIP preferences | Priority + minimum personal money | `PUT /financial-situation` | V, E, G | CI | PASS | — | In the financial situation form |

## G. Profile hub

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| G1 | Profile hub | Situation, (VIP) accounts + financial emails, account & plan, help, log out | — | G | CI | PASS | — | |
| G2 | Financial situation | Plan-scoped sections: income reference (observed vs declared), pay type (monthly / hourly with days, hours, frequency, pay day), essential expenses, debts summary, savings & emergency target, goals, VIP preferences; completeness %; per-field help | `GET/PUT /user-product/financial-situation` | L, E, V, OK | CI | PASS | U | Declared vs observed shown separately (§4.D); Empty field = unknown (null), never zero (§4.D) |
| G3 | Settings — plan | Current plan, change plan with confirmation, promotion copy, billing catalog retry | `/auth/plans`, `/product-ops/billing/catalog`, `POST /auth/plan` | L, E, X | CI | PASS | — | Store billing flag off today; Android: Play Billing 8 panel, server-verified; HUMAN with a Play-signed build; iOS: plan change only; App Store purchase not built (StoreKit + App Store Connect) |
| G4 | Settings — appearance | Theme selector | local | — | PASS | PASS | — | |
| G5 | Settings — security | Linked sign-in methods (Google/Apple link), passkeys list/register when supported | Supabase `getUserIdentities`, `linkIdentity`, passkeys | L, E | — | — | — | Passkeys: evaluate native AuthenticationServices / Credential Manager; Linked identities and passkeys not ported |
| G6 | Settings — app lock | Enable/disable, biometry label, lock now | local | E | CI | HUMAN | — | |
| G7 | Settings — legal | Terms, privacy links | — | — | CI | PASS | — | |
| G8 | Data export | JSON download/share | `GET /auth/me/export` | L, E | CI | PASS | — | Android: JSON shared through a FileProvider cache file; iOS: share sheet from a protected temporary file, removed at launch/sign-out |
| G9 | Account deletion | Destructive confirmation → delete → sign-out | `DELETE /auth/me` | X, L, E | CI | PASS | — | Confirmation, then local sign-out |
| G10 | Log out | Flushes/confirm pending queue (`prepareLogout`) then local sign-out | — | X | PASS | PASS | — | No offline queue to flush (B8) |
| G11 | Free settings / more | Savings summary, links, currency label, plan | `GET /savings-plans` | — | DIFF | DIFF | — | Savings plans live in Goals |

## H. Mail automation (VIP)

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| H1 | Mail status + connections | Connected Gmail/Outlook mailboxes, needs-reconnect state, history scope, disconnect | `GET /vip/gmail/status`, `DELETE /vip/gmail?connection_id` | L, E, X, G | CI | PASS | UI | |
| H2 | Consent + connect | Consent explanation must be accepted; history scope (this month / this year); Gmail or Microsoft; system browser | `POST /vip/gmail/consent`, `/vip/gmail/connect`, `/vip/mail/microsoft/connect` | V, E, G | CI | PASS | U | Gated by `gmail_automation` and VIP; iOS: consent version from /status; locale sent for #288 |
| H3 | OAuth return | Deep link one-time completion, redeem once, retry on network | `POST /vip/mail/oauth/complete` | E, OF | HUMAN | HUMAN | U | HUMAN: real Google/Microsoft consent; Android: one-time completion ledger; mail return URL is a global backend setting (RELEASE_IDENTITY.md); iOS: ASWebAuthenticationSession on `com.finva.app` + onOpenURL for both schemes; one-time ledger; real Google consent is DEVICE REQUIRED |
| H4 | Sync | Manual sync, result counts (auto-saved / pending), partial-period notice | `POST /vip/gmail/sync` | L, E, OK | CI | PASS | — | |
| H5 | Review candidates | Filter, accept, accept with corrections, reject, duplicate/reconciled explanations | `GET /vip/gmail/emails`, `POST/PUT …/accept`, `POST …/reject` | L, E, ∅, OK | CI | PASS | UI | Agent B owns Accept/Reject UX changes — track their PRs; Needs-rate / cannot-convert candidates ask for the user's rate; `already_reviewed` reported |
| H6 | Own-transfer suggestions | Confirm two notices as internal transfer | `GET /vip/gmail/own-transfer-suggestions`, `POST …/own-transfer` | E, OK | CI | PASS | — | |
| H7 | Accounts view | Detected institutions and accounts, confirm own / mark foreign | `GET /vip/financial-identity`, `PUT …/accounts/{id}` | L, E, ∅ | CI | PASS | — | |

## I. Support

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| I1 | Service status | Status + refresh | `GET /product-ops/health` | L, OF | DIFF | DIFF | — | Global health banners (B7); no separate status screen |
| I2 | Guided support chat | Problem / improvement question flow, restart, send | `POST /product-ops/feedback` | V, E, OK | CI | DIFF | U | Warns against secrets; A form (type, subject, details) instead of the guided chat; iOS: form like Android |
| I3 | My reports | List, "resolved?" feedback | `GET /product-ops/feedback`, `PATCH …/resolution` | L, ∅, E | CI | PASS | — | |
| I4 | Support context entry | Opened from errors with prefilled context | — | — | — | — | — | |

## J. Not in scope / not present today

| Item | Status | Notes |
|------|--------|-------|
| Push notifications (Users) | N/A | Not wired in the Users app today |
| Store purchases / restore | Android: Play Billing (server-verified). iOS: BLOCKED (StoreKit + App Store Connect products) | `store_billing` flag off |
| Receipt upload for payment orders | N/A | Unused in UI (finding F6) |
| Owner app | N/A | Owner boundary |

## Change log

| Version | Change |
|---------|--------|
| v1 | Initial inventory from Capacitor source |
| v2 | Native RC (PR "promote DINCR native app from prototype to functional RC"): Android statuses filled from the code and its tests; iOS ported for gates, flags, debts, goals and account deletion |
| v3 | iOS production parity (PR "production parity, release identity and Gmail Email Monitor"): iOS column filled from the code and CI; identity `com.dincr.app` |
