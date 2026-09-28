# Native ↔ FastAPI contract (C4 prototype)

What the native apps send and read, checked against the FastAPI code on `main` (not against
fixtures). iOS `DincrCore` and Android `:core:data` implement the same contract with the same
types and optionality; `AuditTests.swift`/`AuditTest.kt` and `ReauditTests.swift`/`ReauditTest.kt`
pin the same cases on both sides. Fixtures (`Tests/.../Fixtures`, `test/resources`) mirror what
the backend builds.

C4 is a **parallel prototype**. It does not replace the Capacitor app that ships as DINCR v1.0,
and it is not the source of truth for the bundle id, the minimum OS versions or store metadata.

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

`/free/*` serves Free, Basic and VIP (feature minimum `free`); Basic and VIP see a notice that
their full dashboards are still in the current app. Owner/admin sessions stop at a notice.

## Currency rows are read-only here (#269, #273)

The backend's `PUT /free/movements/{id}` without `currency` stores the row as a plain
base-currency amount: for `salary`/`expense` rows it writes `original_amount`,
`original_currency` and `exchange_rate` as NULL, so changing only the description would erase
what the user typed and the rate they entered. The prototype never edits currencies and never
invents a rate, so **a row carrying any of `original_amount`, `original_currency` or
`exchange_rate` is read-only and cannot be deleted from the prototype**, whatever its currency (also when
it equals the base). Rows without a usable `YYYY-MM-DD` date are read-only too, because the
full-replacement `PUT` would have to invent one. The backend's own `editable` flag still applies.

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
  `transactions.amount` (NUMERIC(12,2) in production). `original_amount` NUMERIC(14,2) and
  `exchange_rate` NUMERIC(14,6) are never written by the prototype. Zero, negatives, NaN,
  Infinity, scientific notation, non-ASCII digits and anything ambiguous (`1,000` in
  `dot_comma`, `1.000` in `comma_dot`) are rejected, never guessed.
- Edit forms prefill the stored value unrounded (`inputText`) and send it back digit for digit
  unless the user changes it.

## Compatibility with other work on main

| Work | What the prototype does |
|---|---|
| #269 manual income/expense in CRC/USD | Records in the base currency only (no `currency`/`exchange_rate`); rows with currency data are read-only |
| #273 mail transactions in USD | Read-only (they carry `original_*`, and mail rows are not `editable` for the backend) |
| #266 candidate review | Not used: candidates are neither listed nor reviewed |
| #248 plan lifecycle, #284 store subscriptions | Reads `subscription.plan`/`status` only; no plan change, purchase or restore in the prototype |

## Not in the contract yet

- Editing a movement's currency (sending `currency` + the user's `exchange_rate`).
- `X-Idempotency-Key` is not supported by the backend for PUT/DELETE or profile setup; those are
  full replacements or return 404 on repeat.
