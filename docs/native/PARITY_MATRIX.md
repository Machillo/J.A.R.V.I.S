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

States column abbreviations: **L** loading · **E** error · **∅** empty · **OK** success feedback ·
**X** destructive confirmation · **OF** offline behavior · **G** plan/flag gate · **V** validation.

Every feature row must reach `PASS`, `DIFF`, `HUMAN` or `N/A` on both platforms before the
migration is declared complete.

---

## A. Boot, identity and gating

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| A1 | Release policy gate | Blocking screen when `required`; dismissible banner when `optional` (per platform+version); re-check on resume; fail-open | `GET /product-ops/release-policy` | L, E(fail-open) | — | — | — | Store URL per platform |
| A2 | Login — Google | OAuth PKCE in system browser, callback accepts `code` only | Supabase Auth | L, E | — | — | — | |
| A3 | Login — Apple | iOS only | Supabase Auth (Apple) | L, E | — | N/A | — | Guideline 4.8; Android shows Google only |
| A4 | Session restore / sign-out | Session persists; sign-out is local scope; identity change resets user | Supabase Auth | — | — | — | — | Keychain / Keystore |
| A5 | Identity load error | Retry, support, log out | `GET /auth/me` | E | — | — | — | |
| A6 | Finish pending deletion | Shown when `/auth/me` returns `account_deletion_pending` | `DELETE /auth/me` | L, E, X | — | — | — | |
| A7 | Owner session in Users app | Capacitor routes to Owner app | `/auth/me` role | G | — | — | — | **DIFF**: native Users apps never render Owner features; show "use the Owner app" + sign-out |
| A8 | Legal consent | Two required checkboxes, doc links, version shown, log out | `POST /auth/legal/accept` then `GET /auth/me` | L, E, V | — | — | — | |
| A9 | Profile setup (4 steps) | Name → goal (6 options) → base + extra currencies, number format, symbol position, live preview → institutions (search, 8 banks, logos, "supported" badge) | `POST /auth/profile-setup` | L, E, V | — | — | — | Saved only at the end; back button per step |
| A10 | Welcome story | 5 slides, skip, once per account (local flag) | — | — | — | — | — | |
| A11 | Plan selection | Expandable plan cards, price from billing catalog, paid plans only while promotion active, retry for plans and billing | `GET /auth/plans`, `GET /product-ops/billing/catalog`, `POST /auth/plan` | L, E, G | — | — | — | Plan confirmed from response or fresh `/auth/me` |
| A12 | App lock onboarding | One-time offer to enable biometrics after first login | local | — | — | — | — | |
| A13 | App lock | Biometric or device passcode; 5-min background timeout; unlock / log out; error mapping (cancel, not enrolled, lockout, no passcode) | local | E | — | — | — | HUMAN: Face ID / fingerprint |
| A14 | Profile refresh on resume | Throttled 15 s; only re-render on identity/plan change | `GET /auth/me` | — | — | — | — | |

## B. Shell and cross-cutting

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| B1 | Tab bar (5 tabs) + active-route mapping | Hoy, Movimientos, Plan, DINCR, Perfil; VIP badge when intelligence off | — | G | — | — | — | iOS TabView; Android NavigationBar |
| B2 | Back navigation | In-app stack; Android back pops then minimizes; iOS edge swipe | — | — | — | — | — | Native nav stacks |
| B3 | Header | Plan subtitle, per-plan titles, avatar → settings | `/auth/me` | — | — | — | — | |
| B4 | Feature flags | 5 flags, safe defaults, 60 s refresh, cache | `GET /product-ops/feature-flags` | G | — | — | — | |
| B5 | Writes-paused banner | When `financial_writes` off | flags | G | — | — | — | Also disable write actions |
| B6 | Subscription access notice | Dismissible banner from `subscription.access_notice` | `/auth/me` | — | — | — | — | |
| B7 | Health mode banner | offline / recovering / degraded / outage + "Ver estado" | `GET /product-ops/health`, reachability | OF | — | — | — | NWPathMonitor / ConnectivityManager |
| B8 | Offline write queue | Allow-listed POST/PUT/PATCH queued per user (20 ops, 32 KB, 24 h) with operation id; flush on reconnect/resume; recovered/failed notices | idempotent write endpoints | OF | — | — | — | Decision pending: reproduce with same idempotency contract vs. block writes offline |
| B9 | API error help + incident report | Auto-report incident, show reference, open support | `POST /product-ops/incidents` | E | — | — | — | |
| B10 | Progressive profile nudge | Next missing datum card, dismiss locally | `GET /user-product/financial-situation` | — | — | — | — | |
| B11 | Screen error boundary | Retry + go to support | — | E | — | — | — | |
| B12 | Theme | dark / light / system (live) | local | — | — | — | — | |
| B13 | Language | es / en from device | — | — | — | — | — | String catalogs |
| B14 | Money formatting | Hard-coded CRC (finding F3) | — | — | — | — | — | BLOCKED on Agent B currency contract for multi-currency; native uses profile currency when defined |
| B15 | Product analytics | Screen events + telemetry | `POST /product-ops/events` | — | — | — | — | No PII |
| B16 | Financial disclaimer | Shown under strategy / advisory screens | — | — | — | — | — | |
| B17 | Feature unavailable | Replaces gated screens with server message | flags | G | — | — | — | |

## C. Overview (Hoy)

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| C1 | Free overview | Available this month, income/expenses, debt paid, KPIs, 6-month income vs expense bars, expenses by category, link to monthly summary | `GET /user-product/free/dashboard` | L, E, ∅ | — | — | — | Charts: Swift Charts / Compose Canvas |
| C2 | Basic dashboard | Planned available, budget used %, quick links (budget, commitments, savings), next 7 days commitments, month plan progress | `GET /user-product/basic/dashboard`, `/basic/budget`, `/basic/calendar` | L, E, ∅ | — | — | — | "available"/"used %" computed client-side → backend dependency (audit §5) |
| C3 | VIP dashboard | Strategic available, top actions, recommended priority, 6-month projection summary, plan vs reality, monthly review, DINCR Today | `GET /user-product/vip/command-center`, `/financial-situation`, `/basic/budget`, `POST /vip/lifecycle/snapshots` | L, E(retry), G | — | — | — | Snapshot POST on open (finding F4) |

## D. Movements

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| D1 | Movements list | Search, filter tabs (all / income / expense / debt), sorted by date, read-only rows marked | `GET /user-product/free/movements` | L, E, ∅ | — | — | — | "debt" kind is a client regex → backend dependency |
| D2 | Debts in Movimientos | Debt filter shows debt list (read-only) + "Gestionar" + debt payments | `GET /finance/debts` | L, E, ∅ | — | — | — | |
| D3 | Add income / expense | Chooser sheet → form: amount, description, category (suggestions), date; single-flight | `POST /finance/income`, `POST /finance/expenses` | V, E, OF | — | — | — | |
| D4 | Edit income / expense | Tap editable row → edit sheet | `PUT /finance/income/{id}`, `PUT /finance/expenses/{id}` | V, E, OF | — | — | — | |
| D5 | Full history | Search, type and category filters, edit and delete editable rows | `GET/PUT/DELETE /user-product/free/movements[/{id}]` | L, E, ∅, X | — | — | — | |
| D6 | Delete movement | Confirmation "no se puede deshacer" | `DELETE …` | X, E | — | — | — | |
| D7 | Monthly summary | Month picker, KPIs (income, spent, balance, debt paid, savings, goals %), top category, distribution | `GET /user-product/free/monthly-summary?period` | L, E | — | — | — | |

## E. Plan hub

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| E1 | Plan hub | Grouped links; Budget (Basic+), Calendar + Recurring (Basic+), Emergency + Aguinaldo (VIP) | — | G | — | — | — | |
| E2 | Debts list | Total, progress ring (Free), cards with payment/progress, next payment, months remaining | `GET /finance/debts` | L, E, ∅ | — | — | — | months remaining computed client-side (audit §5) → show backend value only |
| E3 | Debt create / edit | Name, balance, original, monthly payment; Basic+: type, annual interest, term, payment day, next date | `POST/PUT /finance/debts[/{id}]` | V, E, OF | — | — | — | |
| E4 | Debt payment | Amount dialog | `POST /finance/debts/{id}/payments` | V, E, OF | — | — | — | |
| E5 | Debt delete | Confirmation | `DELETE /finance/debts/{id}` | X | — | — | — | |
| E6 | Goals | Total progress, list, detail, create/edit (name, target, saved, date, priority, status), contribute, delete; VIP smart goal card (recommended contribution from backend) | `/user-product/goals*`, `GET /vip/command-center` | L, E, ∅, V, X, OF | — | — | — | |
| E7 | Savings plans | Monthly amount, saved, start/end, status; contribute; delete | `/user-product/savings-plans*` | L, E, ∅, V, X, OF | — | — | — | Free "more" shows savings summary |
| E8 | Budget | Month total spent / budgeted / available, per-category progress, over-limit state, edit limits mode | `GET/PUT /user-product/basic/budget` | L, E, V | — | — | — | |
| E9 | Financial calendar | Month picker, commitments count, known payments, events by day | `GET /user-product/basic/calendar?period` | L, E, ∅ | — | — | — | |
| E10 | Recurring | Summary, list, pause/activate, delete, create (name, amount, category, type, frequency, due day) | `/user-product/basic/recurring*` | L, E, ∅, V, X, OF | — | — | — | |
| E11 | VIP emergency fund (Salvavidas) | Coverage 1/3/6 months, saved balance, protected expenses | `GET/PUT /user-product/vip/salvavidas` | L, E, V, G | — | — | — | Shared PremiumStrategy copy under review (F1) |
| E12 | VIP aguinaldo | Estimate from salaries | `GET /user-product/vip/aguinaldo` | L, E, G | — | — | — | Gated by `gmail_automation` |

## F. DINCR (advisor) hub

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| F1 | Advisor hub | Free → monthly summary; Basic → strategy; VIP → Today, direction, reality, monthly review, projections, scenarios | — | G | — | — | — | |
| F2 | Strategy (Free/Basic) | Month guide, priority, estimated income, known installments, margin, recommended plan, next-income split, debt projection, smart goals, "what if I add more" simulation, director alerts, data gaps | `GET /finance/strategy-basic`, `POST …/simulate` | L, E | — | — | — | Disclaimer below |
| F3 | VIP strategy | Optional actions + PremiumStrategy (sections: salvavidas, investment, debt advisory, allocation, aguinaldo) | `/finance/strategy-vip`, `/vip/strategy-dashboard`, `/vip/debt-advisory`, `/vip/salvavidas`, `/vip/aguinaldo` | L, E, G | — | — | — | F1 review first |
| F4 | VIP recommendation | Recommended action, why, impact | command-center | G | — | — | — | |
| F5 | VIP projections + detail | 6-month evolution, per-debt projection | command-center | G | — | — | — | Charts |
| F6 | VIP scenarios | Presets + custom (extra income, expense change, one-off money), comparison | `POST /finance/strategy-vip/simulate` | L, E, V, G | — | — | — | Read-only simulation |
| F7 | VIP plan vs reality | Budget planned vs spent | budget, command-center | G | — | — | — | |
| F8 | VIP monthly review | Period picker, changes, next priority | `GET /vip/lifecycle/monthly-review` | L, E, G | — | — | — | |
| F9 | VIP Today | Proactive advisor items | `GET /vip/lifecycle/proactive-advisor` | L, E, ∅, G | — | — | — | |
| F10 | VIP preferences | Priority + minimum personal money | `PUT /financial-situation` | V, E, G | — | — | — | |

## G. Profile hub

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| G1 | Profile hub | Situation, (VIP) accounts + financial emails, account & plan, help, log out | — | G | — | — | — | |
| G2 | Financial situation | Plan-scoped sections: income reference (observed vs declared), pay type (monthly / hourly with days, hours, frequency, pay day), essential expenses, debts summary, savings & emergency target, goals, VIP preferences; completeness %; per-field help | `GET/PUT /user-product/financial-situation` | L, E, V, OK | — | — | — | Declared vs observed shown separately (§4.D) |
| G3 | Settings — plan | Current plan, change plan with confirmation, promotion copy, billing catalog retry | `/auth/plans`, `/product-ops/billing/catalog`, `POST /auth/plan` | L, E, X | — | — | — | Store billing flag off today |
| G4 | Settings — appearance | Theme selector | local | — | — | — | — | |
| G5 | Settings — security | Linked sign-in methods (Google/Apple link), passkeys list/register when supported | Supabase `getUserIdentities`, `linkIdentity`, passkeys | L, E | — | — | — | Passkeys: evaluate native AuthenticationServices / Credential Manager |
| G6 | Settings — app lock | Enable/disable, biometry label, lock now | local | E | — | — | — | |
| G7 | Settings — legal | Terms, privacy links | — | — | — | — | — | |
| G8 | Data export | JSON download/share | `GET /auth/me/export` | L, E | — | — | — | |
| G9 | Account deletion | Destructive confirmation → delete → sign-out | `DELETE /auth/me` | X, L, E | — | — | — | |
| G10 | Log out | Flushes/confirm pending queue (`prepareLogout`) then local sign-out | — | X | — | — | — | |
| G11 | Free settings / more | Savings summary, links, currency label, plan | `GET /savings-plans` | — | — | — | — | |

## H. Mail automation (VIP)

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| H1 | Mail status + connections | Connected Gmail/Outlook mailboxes, needs-reconnect state, history scope, disconnect | `GET /vip/gmail/status`, `DELETE /vip/gmail?connection_id` | L, E, X, G | — | — | — | |
| H2 | Consent + connect | Consent explanation must be accepted; history scope (this month / this year); Gmail or Microsoft; system browser | `POST /vip/gmail/consent`, `/vip/gmail/connect`, `/vip/mail/microsoft/connect` | V, E, G | — | — | — | |
| H3 | OAuth return | Deep link one-time completion, redeem once, retry on network | `POST /vip/mail/oauth/complete` | E, OF | — | — | — | HUMAN: real Google/Microsoft consent |
| H4 | Sync | Manual sync, result counts (auto-saved / pending), partial-period notice | `POST /vip/gmail/sync` | L, E, OK | — | — | — | |
| H5 | Review candidates | Filter, accept, accept with corrections, reject, duplicate/reconciled explanations | `GET /vip/gmail/emails`, `POST/PUT …/accept`, `POST …/reject` | L, E, ∅, OK | — | — | — | Agent B owns Accept/Reject UX changes — track their PRs |
| H6 | Own-transfer suggestions | Confirm two notices as internal transfer | `GET /vip/gmail/own-transfer-suggestions`, `POST …/own-transfer` | E, OK | — | — | — | |
| H7 | Accounts view | Detected institutions and accounts, confirm own / mark foreign | `GET /vip/financial-identity`, `PUT …/accounts/{id}` | L, E, ∅ | — | — | — | |

## I. Support

| ID | Feature | Capacitor behavior | API | States | iOS | Android | Tests | Notes |
|----|---------|--------------------|-----|--------|-----|---------|-------|-------|
| I1 | Service status | Status + refresh | `GET /product-ops/health` | L, OF | — | — | — | |
| I2 | Guided support chat | Problem / improvement question flow, restart, send | `POST /product-ops/feedback` | V, E, OK | — | — | — | Warns against secrets |
| I3 | My reports | List, "resolved?" feedback | `GET /product-ops/feedback`, `PATCH …/resolution` | L, ∅, E | — | — | — | |
| I4 | Support context entry | Opened from errors with prefilled context | — | — | — | — | — | |

## J. Not in scope / not present today

| Item | Status | Notes |
|------|--------|-------|
| Push notifications (Users) | N/A | Not wired in the Users app today |
| Store purchases / restore | N/A (flag `store_billing` off) | Revisit when billing ships — Agent A |
| Receipt upload for payment orders | N/A | Unused in UI (finding F6) |
| Owner app | N/A | Owner boundary |

## Change log

| Version | Change |
|---------|--------|
| v1 | Initial inventory from Capacitor source |
