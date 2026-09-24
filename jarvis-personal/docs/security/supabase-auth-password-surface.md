# Supabase Auth: Leaked Password Protection and the password surface

Supabase's security advisor reports `auth_leaked_password_protection` (WARN): *Leaked Password Protection Disabled*. This document evaluates it against how DINCR actually authenticates and prepares the fix, which needs production dashboard changes (**HUMAN GATE**).

## How DINCR authenticates today (from code)

- The app offers only OAuth. `frontend/src/pages/Login.jsx` shows **Continue with Google** everywhere and **Continue with Apple** on iOS/web. `frontend/src/lib/nativeAuth.js` calls only `signInWithOAuth` (PKCE, `skipBrowserRedirect`, deep link `…://auth/callback`). The repository never calls `signUp`, `signInWithPassword`, `signInWithOtp`, `updateUser({ password })` or `resetPasswordForEmail`.
- The backend (`backend/auth/service.py`, `verify_supabase_token` → `authenticate_access_token`) accepts **any** valid Supabase access token. It resolves the DINCR identity **by email**: an unknown email gets a new Free account and Personal workspace, and a known email is re-bound to the token's `supabase_user_id`. Owner is decided by `OWNER_EMAILS`.
- The App/Play reviewer account also signs in with Google or Apple (`backend/scripts/seed_review_demo.py`).

## Production Auth settings (read on 2026-09-23 from the public `GET /auth/v1/settings` endpoint, no changes made)

| Setting | Value | Meaning |
|---|---|---|
| `external.google` | true | used by the app |
| `external.apple` | **false** | the iOS/web **Continue with Apple** button cannot work until this is configured (see below) |
| `external.email` | **true** | email/password sign-up and sign-in are enabled at the API level |
| `disable_signup` | false | anyone can create users |
| `mailer_autoconfirm` | false | email accounts must click a confirmation link before getting a session |

## Real exposure

The UI never offers passwords, but the anon key ships in every app build. Anyone can therefore call `POST /auth/v1/signup` with an email and password directly:

1. **Password accounts outside the product design.** After confirming the email, that person gets a normal DINCR Free account through the email-keyed backend path. This is not privilege escalation: the account is bound to an email they control, and Owner stays tied to `OWNER_EMAILS`, which requires that inbox. Leaked Password Protection is the only thing that would stop weak or breached passwords on those accounts.
2. **Sign-up email abuse.** Unauthenticated sign-ups make Supabase send confirmation emails to arbitrary addresses from DINCR's sender. This costs deliverability and reputation, not data.
3. **Latent risk: account safety depends on `mailer_autoconfirm = false` (HIGH if that toggle ever flips).** The backend never checks how the user authenticated. If "Confirm email" were turned off:
   - **Pre-account takeover.** An attacker signs up with password as `victim@gmail.com` before the victim ever uses DINCR and gets a session immediately, and the backend creates the account. When the victim later signs in with Google, Supabase's automatic identity linking attaches Google to that same user. The attacker keeps a working password and sees everything the victim adds later.
   - **Instant Owner.** `authenticate_access_token` grants Owner to any address in `OWNER_EMAILS`. Registering by password an Owner address that has never signed in to Supabase would give Owner. This would be a **BLOCKER**.
   - Neither case is reachable with today's settings, and neither has been reproduced against production. They should be verified on a non-production Supabase project.
4. **Account re-binding by email (MEDIUM).** On every login the account's `supabase_user_id` is overwritten with the token's user when the email matches (`backend/auth/service.py`, `authenticate_access_token`; `backend/auth/workspace_context.py`). The Owner bridge trusts that id. Two Supabase users can share an email in some cases: SSO/SAML users, or an auth user deleted from the dashboard and created again. When that happens, the newer user silently inherits the existing account.
5. **Owner role is sticky (LOW).** The effective role is written back to `allowed_users.role`, so removing an address from `OWNER_EMAILS` does not remove Owner until that row is changed too.

Impact of leaving Leaked Password Protection off, if nothing else changes: **LOW**. It only matters for accounts created through the API-only password path, which no real DINCR user uses. Items 3 and 4 are the more important findings. Disabling the Email provider (below) closes item 3's attack path at the source. The code hardening at the end closes items 3 and 4 independently of dashboard settings.

## Recommendation (HUMAN GATE: production dashboard)

Preferred order:

1. **Disable the Email provider** (Authentication → Sign In / Providers → Email → off). DINCR is OAuth-only by design, so this removes the whole password surface and makes the leaked-password warning moot.
   - First confirm that no real user depends on it. In the SQL editor, run this aggregate-only query:
     ```sql
     select provider, count(*) from auth.identities group by provider;
     ```
     Also count never-confirmed users (`select count(*) from auth.users where email_confirmed_at is null;`). If `email` identities or leftover unconfirmed sign-ups show up, inspect them (and remove stale unconfirmed ones) before disabling.
   - Keep sign-ups enabled: new Google/Apple users still need to be created.
2. **Enable Leaked Password Protection** (Authentication → Policies/Passwords → *Prevent use of leaked passwords*), whatever you decide in step 1. It is harmless for OAuth users and closes the warning.
   - It checks HaveIBeenPwned with k-anonymity: only a hash prefix leaves Supabase.
   - It applies when a password is set or changed. Sign-ups or changes with a breached password are rejected with `weak_password`.
   - Supabase documents it as a **paid-plan feature**. On the Free plan this step is not available, and the advisor warning will remain even after step 1 has removed the actual risk. That remaining warning is acceptable and should be recorded as such.
3. Optionally, raise the minimum password length and require character classes on the same screen, if the Email provider stays on.

Behavior change for real users: **none** for Google/Apple users, since OAuth logins never go through password checks.

## Post-change validation (manual)

- Android: Google login, logout, login again → same account and data.
- iOS: Google login. Also Apple login once the Apple provider is configured.
- `GET <SUPABASE_URL>/auth/v1/settings` with the anon key shows `external.email: false` (if step 1 was applied).
- Supabase Security Advisor no longer lists `auth_leaked_password_protection`.
- Reviewer demo account (Google) still signs in.

## Related finding: Apple provider disabled

`Login.jsx` offers Sign in with Apple everywhere except Android (iOS and web). App Store guideline 4.8 generally requires it when Google login is offered. In production, `external.apple` is `false`, so that button returns an error today.

Before the iOS submission (**HUMAN GATE**, Apple Developer + Supabase dashboard):
- create a Services ID and a Sign in with Apple key;
- configure the Apple provider in Supabase with the callback URL;
- add the app's redirect `…://auth/callback` to the allowed redirect URLs;
- test on a physical iPhone.

## Recommended code hardening (defense in depth; needs its own reviewed PR)

Checking `email_confirmed_at` alone is **not** enough: with "Confirm email" off, Supabase marks password sign-ups as confirmed immediately. Proposed instead, in `verify_supabase_token` / `authenticate_access_token`:
1. Accept only tokens whose `app_metadata.provider` is `google` or `apple` and whose `app_metadata.providers` does not include `email`. DINCR is OAuth-only by design, and this check holds regardless of dashboard settings. Also require `email_confirmed_at` as an extra condition. Google users and Apple users, including private relay addresses, arrive confirmed.
2. Bind `supabase_user_id` once. Reject a login whose email matches an account already bound to a different `supabase_user_id` instead of re-binding it.

Both change every login, so they need focused tests, a security review and human approval, plus a physical login test on Android and iOS after deploy.
