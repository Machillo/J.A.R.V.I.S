# Pre-release hostile security audit (code)

Scope: current `main` plus the open overnight PRs. Method: read-only review of every router and dependency, OAuth flows, deep links, deletion/export, logs, analytics, database migrations/RLS, secrets and the offline queue. **No production system was queried or changed.**

## Fixed in this PR

| Sev | Finding | Fix |
|---|---|---|
| HIGH | `POST /auth/check-access` was public and returned the full `allowed_users` row (role, status, Supabase id, dates) for any email. That enables account enumeration and reveals Owner/admin accounts. Nothing used it | The route and its public-path entry are removed. A test asserts it is gone |
| MEDIUM | `/notifications/*` (Owner browser push) had no role check. Any user could store any URL as a push endpoint, and `/notifications/test` made the server POST to it and echo the error text (SSRF probe) | Status, VAPID key, subscribe and test are Owner/admin-only (`/cron` stays secret-protected). Endpoints must be HTTPS on a real push service (FCM, Mozilla, Apple, WNS), checked **when saving and again before every send**, so rows stored earlier are never contacted. System pushes (deploy alerts) go only to active Owner/admin subscriptions. Errors are no longer echoed. **HUMAN:** run a read-only query for `notification_subscriptions` rows that belong to non-Owner accounts or fall outside the allowlist, then decide on cleanup |
| MEDIUM | Client-reported incidents could spam support (email + Discord critical pings) without limit | At most 5 support alerts per account per hour. The budget is serialized per account and counts only incidents that actually alerted, so noise cannot mute a real outage. The incident is always recorded |
| LOW | `/email-monitor/statements/reconcile` (Owner tooling) was callable by users. It was scoped to their workspace, but it could trigger runtime DDL | Owner/admin only |
| LOW | Data export included internal `mail_oauth_flows` / `operation_idempotency` rows | Both tables are excluded |
| LOW | Queued offline writes (raw financial request bodies) stayed in `localStorage` for up to 24 h after logout or account deletion | Every explicit logout (menu and app-lock screen) first tries to sync the queue, then asks before discarding anything still unsynced. Account deletion clears the queue silently. A forced sign-out on 401 keeps the queue |

## Fixed in other overnight PRs

| Area | PR |
|---|---|
| Npm advisories | #206 |
| Supabase password surface (doc) | #207 |
| PostHog event loss and privacy | #210 |
| Parsers: amounts, currency, dates, Gmail sender spoofing, fixture PII | #211 |
| Gemini removal and safe parser discovery | #212 |
| OAuth-only sessions | #214 |

## Open: need design or a human decision

- **MEDIUM: an account deletion can be half-done.** The Supabase Auth user is deleted before the database commit (`backend/auth/service.py`, `delete_current_account`).
  - If the commit fails after Auth accepted the deletion, the login is gone but the data remains.
  - Signing in again with the same Google account re-attaches that data (identity re-binding by email).
  - Proposed fix: commit a "pending deletion" tombstone first, then run an idempotent retry of the Auth deletion and cleanup, and refuse login for tombstoned accounts. Needs a fault-injection test.
- **MEDIUM: offline retries can double-write in a narrow window.** The idempotency record (`backend/core/idempotency.py`) is committed separately from the business write.
  - A crash between the write and `complete_operation` makes the key stale after 2 minutes, and the client retries the write.
  - Proposed fix: write the idempotency row in the same transaction, or add a unique `(workspace_id, idempotency_key)` on financial rows. This needs a migration (**HUMAN GATE for production**).
- **MEDIUM: identity is re-bound by email on every login** (known from #207 and #214). Bind `supabase_user_id` once and reject mismatches.
- **LOW:**
  - No rate limiting anywhere (edge or middleware).
  - The owner-bridge key both authenticates and signs 12 h non-revocable tokens.
  - A failed Gmail token revocation on disconnect is swallowed (Microsoft offers no per-token revocation).
  - Tables created at runtime (`ai_*`, some `ensure_*`) don't enable RLS on a fresh database. Production state is unverified: **HUMAN**, run a read-only check.

## Checked and sound

- **Owner-only routers:** all `INTERNAL_ONLY` routers and the `/jarvis`, `users-admin`, product-ops owner and deployment-monitor routes check roles.
- **No horizontal access:** every `/user-product` route that takes an id filters by workspace/account.
- **Plan gating:** enforced server-side (`require_feature`).
- **Gmail/Outlook OAuth:**
  - state is hashed, single-use, bound to the provider and expires in 10 min;
  - PKCE uses S256;
  - the completion code can only be redeemed by the initiating account/workspace;
  - replays are rejected;
  - tokens are kept in Vault.
- **Deep links:** login accepts only a PKCE code; mail returns carry a single-use completion code; no arbitrary navigation; no cleartext traffic; `allowBackup` is off.
- **Crons and webhooks:** fail closed with constant-time secret comparison.
- **Errors, logs and CORS:** 5xx errors are generic, logs hold no tokens or amounts, and CORS uses an explicit allow-list with bearer auth.
- **Database:**
  - the RLS lockdown covers migrated tables;
  - SECURITY DEFINER functions pin `search_path`, with grants revoked;
  - no public views or storage buckets.
- **Secrets:** no secrets tracked in git, and the `VITE_*` values are public-safe.
- **Deletion cascade and export:** deletion cascades through account/workspace foreign keys, deletes Vault secrets and revokes Google tokens. The export is limited to the caller's own account.

## Needs physical or production validation

- The SSRF fix, with VAPID configured on Render (Owner push still works on a real device).
- Account deletion end-to-end on Android and iOS, with a disposable account, then trying to log in again.
- The RLS/grant state of runtime-created tables in production (read-only SQL, human).
