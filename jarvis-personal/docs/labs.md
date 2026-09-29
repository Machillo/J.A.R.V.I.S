# DINCR Labs

DINCR Labs is a local, disposable place to try ideas: parsers, algorithms, failure
modes, synthetic datasets, UX states. It runs on your machine and in CI, costs
nothing, and **cannot reach production**. When isolation and convenience conflict,
Labs fails closed.

```
PRODUCTION                         LABS
-----------                        ----
Real DB (Supabase)       X         Local embedded PostgreSQL (dincr_labs*)
Real OAuth / Supabase    X         Fake auth: synthetic identity, in-process
Real billing (stores)    X         Simulated plan states (labs/billing.py)
Real Gmail / Outlook     X         Synthetic email fixtures + DINCR's real parser
Real users               X         Synthetic users (@labs.invalid, role "user")
AI providers             X         FakeAIProvider (deterministic)
Internet                 X         Loopback only (network guard)
```

What Labs is **not**: a staging server, a copy of production, a place for real
emails or real accounts, a way to ship a feature. Nothing in Labs is deployed or
imported by the backend, the frontend or the native apps.

## Quick start

From `jarvis-personal/` (Python 3.11 with `requirements.txt` and `backend/tests/requirements-pg.txt`):

```bash
python -m labs doctor                      # show isolation status (changes nothing)
python -m labs up                          # start the local DB, build the Labs schema
python -m labs seed --scenario normal      # reset + load 5 synthetic users (free/basic/vip/vip-usd/owner-like)
python -m labs seed --scenario heavy --count 5000
python -m labs parse --list                # email fixtures
python -m labs parse --fixture bac_purchase_usd
python -m labs experiment 001              # email -> parser -> candidate -> Accept/Reject -> transaction
python -m labs experiment 002              # budget use + snowball vs avalanche
python -m labs chaos                       # failure simulation (experiment 003)
python -m labs reset                       # drop and rebuild Labs data
python -m pytest -q labs                   # the Labs test suite (DINCR_REQUIRE_PG_TESTS=1 in CI)
```

Data lives in `~/.dincr-labs/pg` (override with `DINCR_LABS_HOME`). Delete that
folder to destroy the lab completely.

## Isolation: how Labs refuses production

`python -m labs` starts a **launcher** that never imports the backend. It starts
the local database and re-runs Labs in a **child process with an environment
built from scratch**: an allowlist of operating-system variables, `DINCR_ENV=labs`
and the local Labs database URL. Credentials in your shell or in `backend/.env`
never reach it. The child then activates Labs (`labs/runtime.py`), in this order:

1. **Environment identity** (`labs/guard.py`): `DINCR_ENV` must be exactly `labs`.
   The backend itself has no environment switch, so `DINCR_ENV` only means
   something to Labs; setting it on a server does nothing to the backend.
2. **No production settings**: Labs refuses to start if any credential or
   production-reaching setting is present — by exact name (Supabase, Gmail,
   Microsoft, store billing, SMTP, Discord, push, analytics, AI keys, Render…),
   by family prefix (`SUPABASE_`, `OWNER_`, `JARVIS_OWN…`, `GMAIL_`, `DINCR_STORE_`, …)
   and by pattern (`SECRET`, `TOKEN`, `PASSWORD`, `API_KEY`, `WEBHOOK`, …). Empty
   values count. Only names are reported, never values. `PGHOST`/`PGSERVICE`/…
   are refused too (libpq could redirect connections), and `DATABASE_URL` must
   equal the Labs URL.
3. **Local database only**: the URL's hosts (including `host=`/`hostaddr=` in the
   query and multi-host lists) must be loopback or a local socket directory; the
   database name must start with `dincr_labs`; `service`/`passfile`/`sslrootcert`
   are refused; hosting domains and the product domain are refused; a hosted
   pooler login (`postgres.<project-ref>`) on a local port — a tunnel — is refused.
4. **Network guard** (`labs/netguard.py`): every socket connect, `sendto` and name
   lookup outside loopback raises `NetworkBlocked`. This covers `requests`,
   `httpx`, `smtplib`, Google/Microsoft clients, store verification, Discord and
   push alike.
5. **Tunnel check**: the database behind the URL must be empty or carry the Labs
   marker row. A production database (tables, no marker) reached through a local
   port forward is refused *before* the backend is imported. There is no switch
   to skip this.
6. **`backend/.env` disabled**: `import backend` normally loads `backend/.env`
   (without overriding). Labs replaces `dotenv.load_dotenv` before importing the
   backend, then checks the environment again and asserts the backend's
   `DATABASE_URL` is the Labs database. A process that imported the backend
   before activation is refused.

Destructive operations have a second, independent protection: `reset` and every
Labs connection require the Labs marker (or, for the first reset, an empty
database). A database Labs did not create is never dropped or written.

### Maintaining the guard

- A new backend setting that holds a credential or points at a real service must
  be refused by Labs. `labs/tests/test_guard.py` scans every `os.getenv(...)` in the
  backend and fails until the new name is either forbidden in `labs/guard.py` or
  listed as harmless in the test (with a reason).
- New hosted infrastructure (a new domain or provider): add its public hostname
  fragment to `PRODUCTION_MARKERS`. Never put a secret or a real project id in the
  code.
- Every protection has a mutation test (`labs/tests/test_guard_mutations.py`):
  removing it must make the adversarial battery (`labs/tests/adversarial.py`) fail.
  When you add a protection, add the case it exists for and a mutant for it.

## Architecture

```
labs/
  guard.py        environment identity + production denylist (pure)
  netguard.py     loopback-only sockets
  runtime.py      activation order; require_active() for every operation
  db.py           local pgserver, Labs schema, marker, reset
  schema/labs_schema.sql   production-shaped subset (money types verified)
  synthetic.py    deterministic datasets (Decimal, per-column limits)
  limits.py       NUMERIC limits per table/column
  seed.py         writes a dataset into the Labs DB
  email_lab.py    fixtures -> parser -> candidate -> review; fake auth
  email_fixtures/bank_emails.json   invented emails in supported formats
  ai.py           AIProvider interface + FakeAIProvider (no real provider)
  billing.py      simulated plan states (not the entitlement authority)
  chaos.py        failure simulation context managers
  experiments/    001 parser fixture, 002 budget, 003 failure simulation
  tests/          isolation, guards, mutations, data, DB end to end
```

Labs reuses DINCR's **pure business logic** (the bank parser, `canonical_candidate`)
and DINCR's **real commands** (e.g. `review_gmail_candidate`) only against the Labs
database, with a synthetic identity set in-process. It never reuses production
infrastructure: no Supabase auth, no OAuth clients, no store clients, no SMTP,
no push, no analytics.

### Database

The Labs schema is `database/baseline/v1_identity_ownership.sql` plus
`labs/schema/labs_schema.sql`: a **production-shaped subset**, not the production
schema. The repository cannot rebuild production from `database/schema.sql` plus
migrations (the script does not load on a fresh server), so Labs keeps the tables
its experiments use, with the money types verified in the repository
(`transactions` NUMERIC(12,2)/(12,6) as confirmed by gate Q0; salaries/expenses
(14,2) with the exact all-or-nothing currency CHECK of migration 20260928110000;
candidates (18,2); balances (18,2); rates (14,6)). Ownership is canonical
(`workspace_id`, cascade; legacy `user_id` optional).

## Synthetic data

`python -m labs seed --scenario <name> [--seed N] [--count N]`:

| Scenario | Content |
|---|---|
| `empty` | one Free user, no data |
| `normal` | Free, Basic, VIP (CRC), VIP (USD base), owner-like test user; 3 months of history, salaries, expenses, two debts (one overdue), a completed goal, an exceeded budget, recurring items, a week of USD rates, balances |
| `heavy` | one VIP user with exactly `--count` transactions (default 5000) over 24 months |
| `edge` | 0.00, 0.01, the maximum of each column (transactions 9,999,999,999.99 ≠ expenses 999,999,999,999.99), leap day, year end, USD with rate, odd merchant text |
| `broken` | rows the database must refuse (overflow per column, partial or unsupported original currency); the report lists which were refused |

Same `(scenario, seed)` → same rows. Emails are `…@labs.invalid` (RFC 2606: never
deliverable). Every account has role `user`; `owner_like_test` is a plan label, it
never grants the Owner role or Owner configuration. Money is `Decimal`,
quantized to the column's scale, within the column's limit (`labs/limits.py`).

## Email Monitor lab and parser playground

`labs/email_fixtures/bank_emails.json` holds invented messages in formats DINCR's
parsers already support (BAC purchase CRC/USD, refund, MultiMoney credit), plus
cases that must be ignored (rejected transaction, security notice, bank without a
parser, broken template, absurd amount) and a duplicate. Each case records what the
parser returns (golden test). No Gmail, no OAuth.

```bash
python -m labs parse --fixture bac_purchase_usd
python -m labs parse --file my_case.json   # must contain "synthetic": true, subject, sender, body
```

The playground shows bank, parser, kind, type, amount, currency, original amount,
date, sanitized description (long digit runs masked), confidence, reason, dedupe key
and the canonical candidate. It never prints the body.

Supported today: BAC and MultiMoney notifications (plus BAC/Popular/MultiMoney
statements and the CCSS order in the parser package). BN, BCR, Davivienda and
Promerica have **no parser**; Labs does not invent one.

## AI lab

`labs/ai.py` defines an `AIProvider` interface and a deterministic `FakeAIProvider`.
`provider()` refuses every other name. DINCR has no generative-AI runtime for user
data (CLAUDE.md §4.E); a real provider for an experiment needs explicit
authorization, a known cost, a privacy review and secrets outside the repository,
and even then only synthetic data. `labs/tests/test_isolation.py` fails if an AI SDK
or provider endpoint appears under `labs/`.

## Billing and auth labs

- **Billing** (`labs/billing.py`): simulated `(plan, state)` pairs — active,
  expired, cancelled, pending downgrade, courtesy, verification failure — with the
  plan each state allows, following the documented lifecycle. It is for screens and
  experiments; the entitlement authority stays in `backend/auth/plan_lifecycle.py`
  and `backend/product_ops/store_state.py`. No store is called.
- **Auth** (`email_lab.acting_as`): an in-process synthetic identity (ContextVar),
  refused outside an active Labs process, for any role other than `user`, and for
  any email outside `.invalid`. There is no HTTP route, no token and no Supabase
  call.

## Failure simulation

`labs/chaos.py`: `db_unavailable`, `backend_500`, `timeout`, `slow_network`,
`malformed_response`, `oauth_failure`, `parser_failure`,
`billing_verification_failure`, `offline`. Each changes behaviour only inside its
`with` block. `python -m labs chaos` runs experiment 003 and prints what DINCR's own
code raises in each case.

## Experiments

An experiment is a module in `labs/experiments/` with `run() -> dict`, registered in
`labs/experiments/__init__.py`. It calls `runtime.require_active()`, resets and seeds
what it needs, and returns a JSON-serialisable result. Keep them small.

| ID | What it shows |
|---|---|
| 001 | Synthetic BAC emails → real parser → candidates → real Accept/Reject. A USD purchase without a rate is refused (422); with the user's rate 505 it is saved as ₡10,605 with the original USD 21 — never the parser's matching-only ₡10,395. Duplicates share a dedupe key. |
| 002 | Budget use per synthetic user and debt payoff months/interest, snowball vs avalanche (Labs-only algorithm, Decimal). |
| 003 | Failure simulation against real backend functions. |

## From Labs to DINCR (promotion)

```
IDEA → LAB EXPERIMENT → VALIDATED → PRODUCTION DESIGN → NORMAL PR → TESTS → REVIEW → DINCR
```

Nothing is promoted automatically. The backend cannot import `labs` (tested), so an
experiment that works in Labs has no path into DINCR except a normal PR that
re-implements it under the usual rules (CLAUDE.md: tenancy, read-only reads,
declared vs discovered data, no generative AI, privacy, tests that fail without the
change, human review and merge).

## Security review checklist (what Labs must never become)

- No HTTP server, route or endpoint in Labs (tested); no seed/reset/fake-auth
  endpoint anywhere in the backend (the backend never imports Labs).
- No production credential can enter a Labs process (scrubbed child + guard);
  `DINCR_ENV` spoofing on a server has no effect on the backend.
- No remote database, tunnel or libpq redirection (guard + marker check).
- No outbound network except loopback.
- No real email, account, card or merchant in fixtures (tested for card numbers,
  IBANs and non-bank email addresses).
- No secrets committed under `labs/` (tested).
- Table names in Labs SQL come from code constants, never from input; values are
  always parameters. The playground reads a local file only when marked synthetic.

## CI

`jarvis-ci.yml` runs `python -m pytest -q labs` (with `DINCR_REQUIRE_PG_TESTS=1`)
after the backend suite, on the same embedded PostgreSQL. It covers the guards and
their mutation tests, network blocking, activation order, synthetic data, parser
golden fixtures, the Labs database end to end and experiments 001/003.

## Cost

$0: local embedded PostgreSQL (`pgserver`, already a test dependency), no cloud
resource, no paid service, no AI provider.

## Limitations and roadmap

- **Schema subset**: Labs cannot run every backend endpoint (the full production
  schema is not reproducible from the repository). Next: a reviewed, schema-only
  dump (no data) from a restored backup as the Labs baseline — a human gate.
- **Full ingestion path** (`_ingest_message_once`) needs its parse step extracted
  from its database writes before Labs can run it end to end.
- **UI gallery**: not built in v1. Plan: a separate Vite entry (`labs.html`, own
  config) rendering DINCR components with synthetic data, never part of the
  production build, with a CI check that the release bundle contains no Labs code.
  The web/native apps default to the production API when their API URL variable is
  unset; a Labs build must fail instead of falling back.
- **Mobile lab**: the native prototype on `main` already has a fixtures launch mode
  for debug builds. Plan: fake repositories/API/auth/subscriptions/Email Monitor fed
  from `labs/` datasets exported as JSON, used by SwiftUI previews and Compose
  previews only.
- **HTTP-level Labs** (running the FastAPI app against Labs) would need a Labs-only
  auth path; v1 deliberately has none.
