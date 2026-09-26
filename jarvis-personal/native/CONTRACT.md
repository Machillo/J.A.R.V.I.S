# Native ↔ FastAPI contract (C4 prototype)

What the native apps send and read, checked against the FastAPI code on `main` (not against
fixtures). iOS `DincrCore` and Android `:core:data` implement the same contract with the same
types and optionality; `AuditTests.swift` and `AuditTest.kt` pin the same cases on both sides.
Fixtures (`Tests/.../Fixtures`, `test/resources`) mirror what the backend builds.

## Transport (both platforms)

| Rule | iOS `APIClient` | Android `ApiClient` |
|---|---|---|
| Auth | `Authorization: Bearer <Supabase access token>` | same |
| Headers | `Accept`, `Accept-Language`, `X-Request-ID` (stable across retries), `X-Retry-Attempt` | same |
| Timeout | 20 s per attempt | 20 s call timeout |
| Retries | GET/HEAD only, 2 retries on 408/425/429/502/503/504 and network loss | same |
| Writes | never retried; creates send `X-Idempotency-Key` | same |
| 401 | one forced refresh, then the request once more | same |
| Cancelled request | `CancellationError` (never shown as "offline") | coroutine cancellation passes through |
| Empty body | decoded as `{}` | same |
| TLS | platform default (ATS / Android default trust, no cleartext) | same |

## Endpoints

| Endpoint | Request | Response fields read (nullable?) | Errors handled |
|---|---|---|---|
| `GET /auth/me` | — | `id` **int**; `email`; `display_name`?; `role` (`user`/`admin`/`owner`); `plan_selected`, `profile_setup_completed` (always bool; missing → unknown → gate stays closed); `base_currency` (backend defaults `CRC`); `number_format`; `currency_placement`; `subscription.plan`/`status`?; `legal.required`? | 401 → refresh/sign out; 403; 409 `account_deletion_pending` (object detail, message shown) |
| `POST /auth/profile-setup` | `display_name` (1–80), `usage_goal` (`debt`,`save`,`partner`,`life_change`,`control`,`explore`), `base_currency` (`CRC`/`USD` from the app), `enabled_currencies`, `number_format`, `currency_placement`, `selected_financial_institutions` (8 known ids) | `{"status","profile"}`; `profile` as `/auth/me` | 422 (list detail → generic copy). Plain UPDATE: a repeat submit is harmless; the app also blocks double taps |
| `GET /user-product/free/dashboard` | — | `month`; `income`, `expenses` (numbers); `debt_paid`, `debt_balance`, `balance`, `available_after_commitments` (read as optional; backend always sends them); `categories[{category, amount}]`; `monthly_history` (always 6 months, oldest first, zero-filled) | 401, 402, 403, 5xx |
| `GET /user-product/free/movements` | no query parameters (whole history) | rows: `movement_id` (`origin:id`), `source_id` int, `origin`, `transaction_date` (`YYYY-MM-DD`, may be null), `description`?, `amount` (positive), `transaction_type` (`income`/`expense` only; debt payments arrive as read-only `expense`), `category`?, `notes`, `editable`; from PR #269: `original_amount`?, `original_currency`? | 401, 402, 403, 5xx |
| `POST /user-product/finance/income` · `/expenses` | `amount` (>0), `description`, `category`, `entry_date` (`YYYY-MM-DD`); header `X-Idempotency-Key` | stored row (ignored) | 409 idempotency conflict, 422, 503 `feature_temporarily_unavailable` |
| `PUT /user-product/free/movements/{id}` | full replacement: `transaction_date`, `description`, `amount` (>0), `transaction_type` (unchanged), `category`, `notes` | `{"status","movement_id"}` | 404 (deleted elsewhere → list refreshed), 422, 503 |
| `DELETE /user-product/free/movements/{id}` | — | `{"status","movement_id"}` | 404 (already gone → list refreshed), 422, 503 |

`/free/*` serves Free, Basic and VIP (feature minimum `free`); Basic and VIP see a notice that
their full dashboards are still in the current app. Owner/admin sessions stop at a notice.

## Error model (same on both platforms)

| Status | Kind | Message |
|---|---|---|
| network loss | offline | "Sin conexión…" (retry offered) |
| timeout | timeout | "La solicitud tardó demasiado…" (retry offered) |
| 401 | sessionExpired | refresh once; a rejected refresh signs out |
| 402 | subscriptionRequired | fixed copy |
| 403 / 404 / 409 / 422 / other 4xx | forbidden / notFound / validation / client | backend `detail` string only for Spanish sessions, otherwise fixed copy; list or object `detail` never shown raw |
| 429 | client (after GET retries) | fixed copy |
| 5xx | server (retry offered) | fixed copy, no backend internals |
| undecodable body | decoding | fixed copy |

## Money

- JSON numbers decode exactly (Swift `Decimal`, Kotlin `BigDecimal`); pinned with
  `999999999999.99` and `0.1`.
- Display: CRC without decimals, others with 2, half away from zero (as the Capacitor app's
  `Intl.NumberFormat`), U+2212 minus, currency never converted. Legacy bases show their code.
- Spoken: ungrouped digits and the unit of the currency shown.
- Input: the user's separator preference; at most 2 decimals and 12 integer digits
  (`NUMERIC(14,2)`); anything ambiguous (`1,000` in `dot_comma`, `1.000` in `comma_dot`) is
  rejected, never guessed.
- Edit forms prefill the stored value unrounded (`inputText`) and send it back untouched unless
  the user changes it.

## Not in the contract yet

- Currency on movements: after PR #269, a row typed in another currency must send `currency` and
  `exchange_rate` back on edit, or the backend turns it into a base-currency amount. The apps
  read `original_currency` and keep such rows read-only until currency editing exists.
- `X-Idempotency-Key` is not supported by the backend for PUT/DELETE or profile setup; those are
  full replacements or return 404 on repeat.
