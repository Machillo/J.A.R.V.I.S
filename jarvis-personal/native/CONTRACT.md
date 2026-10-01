# Native ↔ FastAPI contract (native RC)

What the native apps send and read, checked against the FastAPI code on `main` (not against
fixtures). iOS `DincrCore` and Android `:core:data` implement the same contract with the same
types and optionality; `AuditTests.swift`/`AuditTest.kt` and `ReauditTests.swift`/`ReauditTest.kt`
pin the same cases on both sides. Fixtures (`Tests/.../Fixtures`, `test/resources`) mirror what
the backend builds.

The native RC runs against the live backend but does not yet replace the Capacitor app in the
stores; identity and release decisions are in [RELEASE_IDENTITY.md](RELEASE_IDENTITY.md). Android
and iOS implement every endpoint below (iOS: except store purchases and product events). No backend change was
needed for the RC.

## Launch configuration (both platforms, `LaunchPolicy`)

| Situation | Result |
|---|---|
| Release build | Never fixture data, whatever the launch arguments or extras say |
| Debug build with `-DincrFixtures <scenario>` (iOS) / `dincrFixtures` extra or `dincr.fixtures=true` (Android) | Synthetic fixture data, with the "Modo de demostración" banner |
| Backend values missing (API URL, Supabase URL, anon key) | "Prototipo sin servidor configurado" screen; no data, no silent fixtures |
| API or Supabase URL not HTTPS | Same screen. Plain HTTP only in a Debug build and only to loopback (and the Android emulator's `10.0.2.2`) |
| URL with credentials, query or fragment, or no host | Same screen |

Only the Supabase **anon/publishable** key is ever configured in the apps (git-ignored
`Local.xcconfig` / `local.properties`). `check_public_secrets.py` scans `jarvis-personal/native`.

## Transport (both platforms)

| Rule | iOS `APIClient` | Android `ApiClient` |
|---|---|---|
| Auth | `Authorization: Bearer <Supabase access token>` | same |
| Headers | `Accept`, `Accept-Language`, `X-Request-ID` (stable across retries), `X-Retry-Attempt` | same |
| Timeout | 20 s per attempt | 20 s call timeout |
| Retries | GET/HEAD only, 2 retries on 408/425/429/502/503/504 and network loss | same |
| Writes | never retried; creates send `X-Idempotency-Key` | same |
| 401 | one forced refresh, then the request once more | same |
| Redirects | never followed (`RefuseRedirects` per-task delegate; wiring against a live `URLSession` needs a Mac to prove, see R3 N40): a 3xx is an error, so no token is replayed to another URL | `followRedirects(false)`, `followSslRedirects(false)` |
| Cancelled request | `CancellationError` (never shown as "offline") | coroutine cancellation passes through |
| Empty body | decoded as `{}` | same |
| TLS | platform default (ATS not weakened, no cleartext) | same (no cleartext, no network security exceptions) |

## Session (both platforms, `SessionManager`)

- Stored in the Keychain (`WhenUnlockedThisDeviceOnly`) / Android Keystore-encrypted preferences.
- One refresh at a time **per refresh token**: concurrent requests of the same session share it;
  a request of another session never waits for it or receives its tokens.
- A refresh result is saved only if the session that asked is still the current one. After a
  sign-out or another sign-in it is dropped (`sessionChanged`), and a rejected refresh of an old
  session never signs out the new one.
- A caller that goes away (cancellation) never counts as a rejected refresh, and a refresh that
  was sent is always recorded (Supabase has already rotated the token).
- Only 400/401/403 on the token endpoint end the session; 3xx, 408, 425, 429 and 5xx are
  transient ("offline").
- A request that read a session just before another refresh rotated it uses the rotated session
  instead of replaying a spent token; if another account signed in meanwhile it gets
  `sessionChanged`, never the other account's token.
- An identity (`/auth/me`) answer that arrives after sign-out or another sign-in is ignored.
- Sign-out clears the device session first, then tells Supabase (best effort): no request can use
  the session while that call is in flight.

## Endpoints

| Endpoint | Request | Response fields read (nullable?) | Errors handled |
|---|---|---|---|
| `GET /auth/me` | — | `id` **int**; `email`; `display_name`?; `role` (`user`/`admin`/`owner`); `plan_selected`, `profile_setup_completed` (always bool; missing → unknown → gate stays closed); `base_currency` (backend defaults `CRC`); `number_format`; `currency_placement`; `subscription.plan`/`status`?; `legal.required`? (`entry_currencies`, `enabled_currencies` are not used: the prototype records in the base currency only) | 401 → refresh/sign out; 403; 409 `account_deletion_pending` (object detail, message shown) |
| `POST /auth/profile-setup` | `display_name` (1–80), `usage_goal` (`debt`,`save`,`partner`,`life_change`,`control`,`explore`), `base_currency` (`CRC`/`USD`), `enabled_currencies` (`CRC`/`USD`), `number_format`, `currency_placement`, `selected_financial_institutions` (8 known ids) | `{"status","profile"}`; `profile` as `/auth/me` | 422 (list detail → generic copy). Plain UPDATE: a repeat submit is harmless; the app also blocks double taps |
| `GET /user-product/free/dashboard` | — | `month`; `income`, `expenses` (numbers, base currency); `debt_paid`, `debt_balance`, `balance`, `available_after_commitments` (read as optional; backend always sends them); `categories[{category, amount}]`; `monthly_history` (always 6 months, oldest first, zero-filled) | 401, 402, 403, 5xx |
| `GET /user-product/free/movements` | no query parameters (whole history) | rows: `movement_id` (`origin:id`), `source_id` int, `origin`, `transaction_date` (`YYYY-MM-DD`, may be null), `description`?, `amount` (positive, base currency), `transaction_type` (`income`/`expense` only), `category`?, `notes`, `editable`; `original_amount`?, `original_currency`?, `exchange_rate`? (#269 manual entries, #273 mail transactions) | 401, 402, 403, 5xx |
| `POST /user-product/finance/income` · `/expenses` | `amount` (>0, ≤ 9 999 999 999.99), `description`, `category`, `entry_date` (`YYYY-MM-DD`); header `X-Idempotency-Key`. Never `currency`/`exchange_rate`: the amount is in the base currency | stored row (ignored) | 409 idempotency conflict, 422, 503 `feature_temporarily_unavailable` |
| `PUT /user-product/free/movements/{id}` | full replacement: `transaction_date`, `description`, `amount` (>0, ≤ 9 999 999 999.99), `transaction_type` (unchanged), `category`, `notes`. Never `currency`/`exchange_rate` | `{"status","movement_id"}` | 404 (deleted elsewhere → list refreshed), 422, 503 |
| `DELETE /user-product/free/movements/{id}` | — | `{"status","movement_id"}` | 404 (already gone → list refreshed), 422, 503 |

`/free/*` serves Free, Basic and VIP (feature minimum `free`). The Owner uses it at VIP level
(plus the native JARVIS UI, Owner only); admin sessions stop at a notice.

**JARVIS chat (Owner, J1).** `POST /jarvis/chat` `{"message"}` → an untyped dict: `message` (required,
shown as is), `intent`, `status`, `pending`, `action_type`, `data` (shape per intent, read only for
`data.current_field`). Since J2 the chat's scope is quick payroll records (OT/VGH/holiday, bonus) and
the agenda (an explicit "Agendá/Recordame … <fecha>" is always a calendar event; "¿qué tengo?"); any
other request answers `status: UNSUPPORTED` with a short "not available in JARVIS Chat" and runs no
other engine. A change the chat understood (payroll/OT/VGH/holiday, bonus, calendar event) answers
`status: PENDING, pending: true,
data.current_field: "confirm"` with what will be saved (a payroll event also shows its computed
amount); it is saved only when the next message is "sí" (Confirmar), "no" (Cancelar) drops it. A
message that could answer a pending question but that the router also reads as another request
("Hoy 50000" while a bonus amount is asked, "¿qué tengo?") answers `data.current_field: "clarify"`: the app
offers "Es la respuesta" / "Es otra consulta" (sent as those words). The first uses the held text as
the answer; the second answers it as a normal request and keeps the pending action (reply carries
`pending_action`; `current_field: "confirm"` there still offers Confirmar). Never retried automatically. The conversation is kept in memory for the session only; no message is stored.

**JARVIS agenda (Owner, J2).** `GET /jarvis/calendar/upcoming?days=45` → `{"events": [...]}`: rows of the
historical `events` table (`id`, `title`, `event_date` as stored text "YYYY-MM-DD" or
"YYYY-MM-DD HH:MM", optional `event_type`, `description`), from today to 45 days out, in chronological
order; a stored date that is not a real day is left out, never reinterpreted. The apps read it
defensively (an unreadable row is dropped, a body without `events` is an error), group by day for
display and show the time only when the text has one. It is read-only: events are created through
the chat (a confirmed "Agendá …"), which the "¿Qué tengo?" chat answer shares with the agenda.

### RC endpoints (added after C4)

Every write below sends only what the user typed, bounded by the money rules; creates and
payments carry `X-Idempotency-Key` (`^[A-Za-z0-9_-]{8,80}$`, reused only when the same
submission is retried). The plan gate in the app mirrors `BUILTIN_FEATURE_MIN_PLAN`; the backend's
402/403 still decides.

| Area | Endpoints | Notes |
|---|---|---|
| Gates | `POST /auth/legal/accept`, `GET /auth/plans`, `GET /product-ops/billing/catalog`, `POST /auth/plan`, `DELETE /auth/me` | Legal versions come from `/auth/me.legal`; `consent_version` is the backend default `regular-2027-v1`; paid plans only while the promotion is active |
| Operations | `GET /product-ops/feature-flags`, `GET /product-ops/health`, `GET /product-ops/release-policy`, `POST /product-ops/events` | Unknown flags use the backend's safe defaults (writes, mail and store off); release policy fails open; events carry allow-listed screen names only |
| Movements | `GET /free/monthly-summary?period`, `PUT /free/movements/{id}` with `currency` + `exchange_rate` | See "Currency edits" |
| Debts | `GET/POST /finance/debts`, `PUT/DELETE /finance/debts/{id}`, `POST /finance/debts/{id}/payments` | Edit needs Basic; a payment larger than the balance is capped by the backend |
| Goals and savings | `/goals`, `/goals/{id}`, `/goals/{id}/contributions`, `/savings-plans…` | Contribution date validated before sending |
| Situation | `GET/PUT /financial-situation` | An empty field is sent as null (unknown), never zero; observed income is never copied into a declared value; `work_days_per_week` (1–7) is required for **every** income type (historical contract, NOT NULL column): the form always asks it (5 when there is no profile, visible and editable) |
| Basic | `/basic/dashboard`, `/basic/budget` (GET/PUT), `/basic/calendar?period`, `/basic/recurring…`, `/basic/reports?period`, `/finance/strategy-basic` | Strategy Basic: declared income first; without it the observed income of the income policy, never persisted; `income_source` = `declared`/`observed`/`none` (the app labels an estimate) |
| VIP | `/vip/command-center`, `/vip/strategy-dashboard` (Estrategia + Distribución), `GET/PUT /vip/salvavidas`, `/vip/aguinaldo` (409 → not applicable; paused by `vip_intelligence`), `/vip/lifecycle/monthly-review`, `/vip/lifecycle/proactive-advisor` | `POST /vip/lifecycle/snapshots` is **not** called (reads do not write). The strategy dashboard and the Salvavidas answer the neutral Users model (`scope: "users"`); the Owner's personal rules run only for the server Owner role (see "Plan") |
| Mail (VIP) | `/vip/gmail/status`, `/consent`, `/connect`, `/vip/mail/microsoft/connect`, `/vip/mail/oauth/complete`, `/sync`, `/emails` (`?status`, `?bank`, `?financial_account_id`), `/candidates` (+ accept / correct / reject), own-transfer suggestions, `/vip/financial-identity` accounts | Correos and Cuentas are two surfaces of the same candidates: Cuentas reads `/emails?bank=` / `?financial_account_id=` and reviews with the same endpoints; rows carry `financial_account_id`, `bank_movement`, `financial_effect`; no balance is shown. `/emails` answers `{status, items}` (not a bare list); `/sync` answers `failed_connections` as a **list of connection ids**; `/status.connections` includes `disabled` rows, which are hidden; `/connect` body is `{import_scope, locale}` (`en`/`es`); a missing `account_base_currency` is CRC; `resolution_reason` is an internal code, never shown raw. A candidate in another currency without a usable rate asks for the user's rate; `already_reviewed` is reported, not treated as an error; the OAuth return is completed once (ledger) |
| Store | `/product-ops/billing/store/catalog`, `/entitlement`, `/customer-token`, Google verification | The app never grants a plan; the backend verifies every purchase token |
| Support | `GET/POST /product-ops/feedback`, resolution | |
| Export | `GET /auth/me/export` | Shared as a file from the app cache, never logged |

## Plan, Strategy and Owner analysis

- Plan holds only Aguinaldo, Estrategia, Salvavidas and Distribución. Deudas and Metas live in Hoy;
  Presupuesto, Calendario and Recurrentes in Perfil → Finanzas.
- Three strategy contracts: Basic `/finance/strategy-basic`; VIP `/vip/strategy-dashboard`
  (`scope: "users"`: income policy, calendar month ledger, recurring items, debts; cash is unknown,
  `distributable_account_cash: null`); Owner `/jarvis/premium/strategy-dashboard` (`scope: "owner"`:
  the historical JARVIS inputs — salary/deductions/OT/VGH/holidays/bonuses, his pay cycle, cash,
  Casa/Línea obligations, investments). Distribución reads the same answer (`allocations` for Basic,
  `allocation_items` + `distribution_formula` for VIP and Owner).
- Salvavidas: Users get 1/3/6 months of their real obligations (debt payments + recurring expense items)
  against their declared savings (unknown stays unknown); `PUT` takes `target_months` and/or
  `current_amount` (the declared savings). The Owner keeps his historical model (`scope: "owner"`).
- Owner "Análisis financiero" (JARVIS section): `GET /transactions/analysis/summary`,
  `/finance/engine`, `/finance/net-worth` (owner/admin routes). `/finance/net-worth` stores a net-worth
  snapshot on read (historical Owner behaviour).

## Currency edits (#269, #273)

The backend's `PUT /free/movements/{id}` without `currency` stores the row as a plain
base-currency amount: for `salary`/`expense` rows it writes `original_amount`,
`original_currency` and `exchange_rate` as NULL, so changing only the description would erase
what the user typed and the rate they entered.

- **Android** edits a manual (`salary`/`expense`) row typed in another currency only when its
  data is complete (`original_amount`, `original_currency` in the account's entry currencies,
  `exchange_rate` > 0, a valid date): the editor opens in that currency with the original amount
  and the stored rate, and sends `currency` + `exchange_rate` back, so the backend recomputes the
  same base amount. A new foreign entry asks for the user's rate (prefilled with the user's own
  latest rate, never a market rate). Mail rows and partial data stay read-only.
- **iOS** follows the same rules (`Movement.isCurrencyEditable`, `canEdit`, `acceptsCurrency`;
  pinned by `CurrencyEditTests`).
- Rows without a usable `YYYY-MM-DD` date are read-only on both, because the full-replacement
  `PUT` would have to invent one. The backend's own `editable` flag still applies.

## Error model (same on both platforms)

| Status | Kind | Message |
|---|---|---|
| network loss | offline | "Sin conexión…" (retry offered) |
| timeout | timeout | "La solicitud tardó demasiado…" (retry offered) |
| 3xx (redirects are not followed) | server | fixed copy |
| 401 | sessionExpired | refresh once; a rejected refresh signs out |
| 402 | subscriptionRequired | fixed copy |
| 403 / 404 / 409 / 422 / other 4xx | forbidden / notFound / validation / client | backend `detail` string only for Spanish sessions, otherwise fixed copy; list or object `detail` never shown raw |
| 429 | client (after GET retries) | fixed copy |
| 503 `feature_temporarily_unavailable` | featureUnavailable (not retried) | backend message for Spanish sessions, otherwise fixed copy; the paused flag is kept |
| 5xx | server (retry offered) | fixed copy, no backend internals |
| undecodable body | decoding | fixed copy |

## Money

- JSON numbers decode exactly (Swift `Decimal`, Kotlin `BigDecimal`); never `Double`/`Float`.
  Pinned with `999999999999.99` (display of a stored value) and `0.1`.
- Display: CRC without decimals, others with 2, half away from zero (as the Capacitor app's
  `Intl.NumberFormat`), U+2212 minus, currency never converted. Legacy bases show their code.
  Hiding CRC decimals is visual only: the stored cents are kept and edited as they are.
- Spoken: ungrouped digits and the unit of the currency shown.
- Input: the user's separator preference; at most 2 decimals; at most **9 999 999 999.99**
  (10 integer digits). Every field this input writes is bounded by 12,2: `salaries.amount` and
  `expenses.amount` (the backend refuses more, `entry_currency.MAX_AMOUNT`, which holds them to
  12,2 because their production type is not verified; `schema.sql` says 14,2) and
  `transactions.amount` (NUMERIC(12,2) in production). Amount fields the backend does not bound
  (debts, goals, savings plans, budget, recurring, situation) are bounded to the same maximum by
  the client. Exchange rates: > 0, ≤ 100 000, at most 6 decimals (`exchange_rate` NUMERIC(14,6));
  only the user's own rate is ever sent. Zero, negatives, NaN,
  Infinity, scientific notation, non-ASCII digits and anything ambiguous (`1,000` in
  `dot_comma`, `1.000` in `comma_dot`) are rejected, never guessed.
- Edit forms prefill the stored value unrounded (`inputText`) and send it back digit for digit
  unless the user changes it.

## Compatibility with other work on main

| Work | What the prototype does |
|---|---|
| #269 manual income/expense in CRC/USD | Both: create and edit in the entry currencies with the user's own rate |
| #273 mail transactions in USD | Read-only (they carry `original_*`, and mail rows are not `editable` for the backend) |
| #266 candidate review | Both: accept / correct / reject with `already_reviewed` handled |
| #248 plan lifecycle, #284 store subscriptions | Android: plan change with the backend's answer (`plan_kept`, `downgrade_scheduled`…), Play Billing purchase verified by the backend. iOS: plan change; no App Store purchase yet |

## Not in the contract yet

- iOS: App Store purchases (StoreKit) and product analytics events.
- `X-Idempotency-Key` is not supported by the backend for PUT/DELETE or profile setup; those are
  full replacements or return 404 on repeat.

## Email Monitor details (verified against the backend for the iOS port)

- `GET /vip/gmail/emails?status=` answers `{status, items}` (at most 200, newest first); `status`
  is `pending|auto_saved|confirmed|rejected|duplicate` or empty.
- `POST /vip/gmail/sync` answers `failed_connections` as a **list of connection ids**.
- `/vip/gmail/status.connections` includes disabled rows; the apps hide `status == "disabled"`.
- `POST /vip/gmail/connect {import_scope: current_month|current_year, locale}`; `locale` (the app
  language) sets Google's `hl` (#288). The backend builds the Google URL with exactly
  `https://www.googleapis.com/auth/gmail.readonly`, PKCE and `prompt=consent select_account`.
- The provider returns through the backend callback to the global `FINVA_GMAIL_RETURN_URL`
  (`<scheme>://gmail/callback?gmail=<status>&flow&completion&ret`); only the session that started the
  flow can redeem `POST /vip/mail/oauth/complete {flow, completion}` (10 min, single use).
- Errors below 500 are `{"detail": "<Spanish text>"}` only; a notice that needs a rate or cannot be
  converted is derived by the client from `currency`, `original_*` and `account_base_currency`
  (base CRC when absent).
